"""Step 4 baseline: do hazard queries rank positive clips above negatives?

Scores every fully indexed batch-A clip by cosine similarity between a Cosmos-Embed1 query
embedding and its stored segment vectors (caption-text and visual), aggregated per clip.
Writes results/baseline_search.md.
"""
import csv
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
import vdb  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
QUERIES = ["vehicle ahead braking suddenly", "car cutting into our lane", "pedestrian stepping into the road"]


def clip_scores(rows, qvec):
    per = {}
    for r in rows:
        t = float(np.dot(qvec, r["vectors"]))
        v = float(np.dot(qvec, r["vectors_visual"]))
        per.setdefault(r["original_video"], []).append((r["segment_number"], t, v))
    out = {}
    for ov, segs in per.items():
        segs.sort()
        out[ov] = {"text_max": max(s[1] for s in segs), "visual_max": max(s[2] for s in segs),
                   "text_last": segs[-1][1], "visual_last": segs[-1][2]}
        out[ov]["hybrid_max"] = 0.5 * out[ov]["text_max"] + 0.5 * out[ov]["visual_max"]
    return out


def main():
    labels = {r["id"]: int(r["target"]) for r in csv.DictReader(open(ROOT / "data/nexar/labels_public.csv"))}
    man = [r for r in csv.DictReader(open(ROOT / "manifests/batch_a.csv")) if r["index_status"] == "full"]
    ov2id = {r["original_video"]: r["nexar_id"] for r in man}
    rows = vdb.fetch_segments(ov2id)
    qvecs = vdb.embed_text(QUERIES)

    y = np.array([labels[ov2id[ov]] for ov in ov2id])
    lines = [f"# Step 4 baseline: hazard-query similarity (batch A, {len(y)} fully indexed clips, "
             f"{int(y.sum())} positive)", "",
             f"Random ranking AP = {y.mean():.3f}, AUC = 0.500.", "",
             "| Query | Signal | AP | ROC AUC | Positives in top 50 |", "|---|---|---|---|---|"]
    combo = np.zeros(len(y))
    for q, qv in zip(QUERIES, qvecs):
        sc = clip_scores(rows, qv)
        for key in ("text_max", "visual_max", "hybrid_max", "text_last", "visual_last"):
            s = np.array([sc[ov][key] for ov in ov2id])
            if key == "hybrid_max":
                combo += (s - s.mean()) / s.std()
            top50 = int(y[np.argsort(-s)[:50]].sum())
            lines.append(f"| {q} | {key} | {average_precision_score(y, s):.3f} | {roc_auc_score(y, s):.3f} | {top50}/50 |")
    top50 = int(y[np.argsort(-combo)[:50]].sum())
    lines.append(f"| all three (z-scored hybrid sum) | hybrid_max | {average_precision_score(y, combo):.3f} | "
                 f"{roc_auc_score(y, combo):.3f} | {top50}/50 |")
    out = ROOT / "results" / "baseline_search.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
