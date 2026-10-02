"""Step 7: per-clip collision-risk score for batch A, plus evaluation.

Components (all computed uniformly for every clip, no labels used):
  precursor  Cosmos Reason structured caption (prompts/precursor_v1.txt), weighted toward the last segment
  llm        W&B LLM judge over the clip's captions (results/llm_judge.jsonl), optional
  search     Cosmos-Embed1 similarity of hazard queries to segment visual embeddings, last-segment weighted
  yolo       in-path proximity, looming and vulnerable-road-user counts in the final 0.5 s

Blend weights are fixed a priori (WEIGHTS), not fitted on the evaluation labels.

Outputs:
  results/clip_scores.csv        per-clip score, components, cause, cues, summary (no labels)
  results/submission_public.csv  id,score  (sample_submission format)
  results/metrics.md             AP / ROC AUC, ablations, breakdowns when Nexar metadata is present
"""
import csv
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from risk_parse import parse  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
NEXAR = ROOT / "data" / "nexar"
HAZARD_QUERIES = ["vehicle ahead braking suddenly", "car cutting into our lane", "pedestrian stepping into the road"]
STRONG_CUES = {"hard_braking_ahead", "cut_in", "vehicle_crossing_path", "oncoming_in_lane",
               "pedestrian_in_path", "cyclist_in_path"}
WEIGHTS = {"precursor": 0.40, "llm": 0.25, "search": 0.20, "yolo": 0.15}
LAST_W = 0.65


def z(x):
    x = np.asarray(x, dtype=float)
    x = np.where(np.isnan(x), np.nanmean(x), x)
    return (x - x.mean()) / (x.std() + 1e-9)


def load_precursor():
    by_id = defaultdict(list)
    for line in (RES / "precursor_captions.jsonl").open():
        r = json.loads(line)
        by_id[r["nexar_id"]].append(r)
    out = {}
    for nid, segs in by_id.items():
        segs.sort(key=lambda r: r["segment_number"])
        parsed = [parse(s["caption"]) for s in segs]
        risks = [p["risk"] if p["risk"] is not None else 0.0 for p in parsed]
        last = parsed[-1]
        p_score = LAST_W * risks[-1] + (1 - LAST_W) * max(risks)
        p_score += 0.5 * bool(last["cues"] & STRONG_CUES) + 0.5 * (last["ttc"] is not None and last["ttc"] <= 2)
        peak = max(range(len(parsed)), key=lambda i: (risks[i], i))
        out[nid] = {"precursor": p_score, "risk_last": risks[-1], "risk_max": max(risks),
                    "cause": parsed[peak]["cause"] or "none", "peak_segment": segs[peak]["segment_number"],
                    "cues": sorted(set().union(*(p["cues"] for p in parsed))),
                    "summary": parsed[peak]["summary"] or "", "structured": all(p["structured"] for p in parsed),
                    "n_segments": len(segs)}
    return out


def load_search(ids):
    import vdb  # deferred: needs network only for the query embeddings
    vecs = np.load(ROOT / "data" / "cache" / "visual_vectors.npz")
    manifest = {r["nexar_id"]: r for r in csv.DictReader(open(ROOT / "manifests/batch_a.csv"))}
    q = vdb.embed_text(HAZARD_QUERIES)
    per_query = []
    for qi in range(len(HAZARD_QUERIES)):
        vals = []
        for nid in ids:
            stem = manifest[nid]["original_video"].rsplit("/", 1)[1][:-4]
            sims = [(k, float(vecs[k] @ q[qi])) for k in vecs.files if f"/{stem}_segment_" in k]
            sims.sort()
            vals.append(LAST_W * sims[-1][1] + (1 - LAST_W) * max(s for _, s in sims))
        per_query.append(z(vals))
    return dict(zip(ids, np.mean(per_query, axis=0)))


def load_yolo():
    out = {}
    for r in csv.DictReader(open(RES / "yolo_features.csv")):
        out[r["nexar_id"]] = {k: float(r[k]) for k in ("prox_last", "looming", "vru_in_path")}
    return out


def load_llm():
    path = RES / "llm_judge.jsonl"
    if not path.exists():
        return {}
    out = {}
    for line in path.open():
        r = json.loads(line)
        try:
            out[r["nexar_id"]] = float(r["llm_risk"])
        except (TypeError, ValueError):
            pass
    return out


def load_labels():
    labels = {r["id"]: int(r["target"]) for r in csv.DictReader(open(NEXAR / "labels_public.csv"))}
    meta = {}
    for sub in ("positive", "negative"):
        p = NEXAR / "test-public" / sub / "metadata.csv"
        if p.exists():
            for r in csv.DictReader(open(p)):
                meta[Path(r["file_name"]).stem] = r
    return labels, meta


def ap_auc(y, s):
    return average_precision_score(y, s), roc_auc_score(y, s)


def main():
    pre = load_precursor()
    ids = sorted(pre)
    yolo, llm = load_yolo(), load_llm()
    search = load_search(ids)

    comp = {
        "precursor": z([pre[i]["precursor"] for i in ids]),
        "search": np.array([search[i] for i in ids]),
        "yolo": z([z([yolo[i]["prox_last"] for i in ids])[k] + 0.5 * z(np.log([yolo[i]["looming"] for i in ids]))[k]
                   + 0.5 * z([yolo[i]["vru_in_path"] for i in ids])[k] for k in range(len(ids))]),
    }
    weights = dict(WEIGHTS)
    if len(llm) >= 0.95 * len(ids):
        comp["llm"] = z([llm.get(i, np.nan) for i in ids])
    else:
        weights.pop("llm")
    total_w = sum(weights.values())
    final = sum(weights[k] * comp[k] for k in weights) / total_w
    score = 1 / (1 + np.exp(-final))

    with open(RES / "clip_scores.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "score", "rank", "precursor_z", "search_z", "yolo_z", "llm_z", "risk_last", "risk_max",
                    "llm_risk", "cause", "peak_segment", "cues", "summary"])
        order = np.argsort(-score)
        rank = {ids[j]: r + 1 for r, j in enumerate(order)}
        for k, i in enumerate(ids):
            w.writerow([i, f"{score[k]:.5f}", rank[i], f"{comp['precursor'][k]:.3f}", f"{comp['search'][k]:.3f}",
                        f"{comp['yolo'][k]:.3f}", f"{comp['llm'][k]:.3f}" if "llm" in comp else "",
                        pre[i]["risk_last"], pre[i]["risk_max"], llm.get(i, ""), pre[i]["cause"],
                        pre[i]["peak_segment"], ";".join(pre[i]["cues"]), pre[i]["summary"]])
    with open(RES / "submission_public.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "score"])
        for k, i in enumerate(ids):
            w.writerow([int(i), f"{score[k]:.5f}"])

    labels, meta = load_labels()
    y = np.array([labels[i] for i in ids])
    lines = ["# MomentOS evaluation: Nexar public test (batch A)", "",
             f"Clips scored: {len(ids)} ({int(y.sum())} positive, {int((1 - y).sum())} negative). "
             f"Random-ranking AP = {y.mean():.3f}.", "",
             f"Blend weights (fixed a priori): {', '.join(f'{k}={v}' for k, v in weights.items())}.", "",
             "## Overall", "", "| Model | AP | ROC AUC |", "|---|---|---|"]
    for name in list(weights) + ["final"]:
        s = final if name == "final" else comp[name]
        a, u = ap_auc(y, s)
        lines.append(f"| {'**final blend**' if name == 'final' else name} | {a:.3f} | {u:.3f} |")
    lines += ["", "## Ablation (drop one component)", "", "| Without | AP | ROC AUC |", "|---|---|---|"]
    for drop in weights:
        ws = {k: v for k, v in weights.items() if k != drop}
        s = sum(ws[k] * comp[k] for k in ws) / sum(ws.values())
        a, u = ap_auc(y, s)
        lines.append(f"| {drop} | {a:.3f} | {u:.3f} |")

    parse_ok = sum(pre[i]["structured"] for i in ids)
    lines += ["", f"Structured-caption parse rate: {parse_ok}/{len(ids)} clips.", ""]

    status = {r["nexar_id"]: r["index_status"] for r in csv.DictReader(open(ROOT / "manifests/batch_a.csv"))}
    full = np.array([status[i] == "full" for i in ids])
    if (~full).any():
        a, u = ap_auc(y[full], final[full])
        pend_neg, full_neg = (~full) & (y == 0), full & (y == 0)
        lines += ["## Checks", "",
                  f"- Like-for-like with `baseline_search.md` (the {int(full.sum())} clips fully indexed at the start, "
                  f"random AP {y[full].mean():.3f}): final blend AP {a:.3f}, ROC AUC {u:.3f}.",
                  f"- Index-completeness bias: all {int((~full).sum())} initially pending clips are negatives. "
                  f"Their mean score is {score[pend_neg].mean():.3f} vs {score[full_neg].mean():.3f} for indexed "
                  "negatives, so missing index rows do not make clips look safer.", ""]

    if meta:
        neg = y == 0
        lines += ["## By time to accident (positives at that horizon vs all negatives)", "",
                  "| time_to_accident | positives | AP | ROC AUC |", "|---|---|---|---|"]
        tta = np.array([meta.get(i, {}).get("time_to_accident", "") for i in ids])
        aps = []
        for t in sorted({v for v in tta[y == 1] if v}):
            m = neg | ((y == 1) & (tta == t))
            a, u = ap_auc(y[m], final[m])
            aps.append(a)
            lines.append(f"| {t} s | {int(((y == 1) & (tta == t)).sum())} | {a:.3f} | {u:.3f} |")
        if aps:
            lines.append(f"| **mean (mAP)** | | **{np.mean(aps):.3f}** | |")
        for field in ("weather", "light_conditions", "scene"):
            vals = np.array([meta.get(i, {}).get(field, "") or "unknown" for i in ids])
            lines += ["", f"## By {field}", "", f"| {field} | clips | positives | AP | ROC AUC |", "|---|---|---|---|---|"]
            for v in sorted(set(vals)):
                m = vals == v
                if y[m].min() == y[m].max():
                    lines.append(f"| {v} | {int(m.sum())} | {int(y[m].sum())} | n/a | n/a |")
                    continue
                a, u = ap_auc(y[m], final[m])
                lines.append(f"| {v} | {int(m.sum())} | {int(y[m].sum())} | {a:.3f} | {u:.3f} |")
        lines.append("")
    else:
        lines += ["Breakdowns by time_to_accident / weather / light / scene need the Nexar "
                  "`test-public/{positive,negative}/metadata.csv` files in `data/nexar/` (gated on Hugging Face).", ""]

    official = NEXAR / "evaluate_submission.py"
    if official.exists() and (NEXAR / "solution.csv").exists():
        r = subprocess.run([sys.executable, str(official), str(RES / "submission_public.csv"),
                            str(NEXAR / "solution.csv")], capture_output=True, text=True)
        lines += ["## Official evaluate_submission.py (Public split only)", "", "```", r.stdout.strip() or r.stderr.strip(), "```", ""]

    (RES / "metrics.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
