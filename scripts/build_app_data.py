"""Build app/static/data.json for the MomentOS web app (no labels, no tags).

Simulated riders: Nexar clips come from anonymous, unrelated drivers. To demo driver-level scoring
we deterministically group clips into SIM_RIDERS synthetic "riders" by hashing the clip id. These
groupings are not real people and are labelled as simulated everywhere in the UI.

Driver score policy (safe-driver, discount-only):
  - only events whose dominant cause is the ego driver count against the driver
  - events caused by other road users are shown but never counted
  - tiers can only grant a discount or offer coaching; there is no surcharge tier
  - any tier change requires human review; drivers can contest an event
"""
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from risk_parse import EGO_CUES, parse  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = ROOT / "app" / "static" / "data.json"
SIM_RIDERS = 24
HIGH_Q, ELEVATED_Q = 0.80, 0.60
SEARCH_WINDOW = ("2026-10-02T19:40:00Z", "2026-10-02T20:20:00Z")


def rider_of(nexar_id):
    return f"R{int(hashlib.sha1(nexar_id.encode()).hexdigest(), 16) % SIM_RIDERS + 1:02d}"


def main():
    manifest = {r["nexar_id"]: r for r in csv.DictReader(open(ROOT / "manifests/batch_a.csv"))}
    scores = {r["id"]: r for r in csv.DictReader(open(RES / "clip_scores.csv"))}
    yolo = {r["nexar_id"]: r for r in csv.DictReader(open(RES / "yolo_features.csv"))}
    llm = {}
    if (RES / "llm_judge.jsonl").exists():
        for line in (RES / "llm_judge.jsonl").open():
            r = json.loads(line)
            llm[r["nexar_id"]] = r
    segs = defaultdict(list)
    for line in (RES / "precursor_captions.jsonl").open():
        r = json.loads(line)
        segs[r["nexar_id"]].append(r)

    all_scores = np.array([float(s["score"]) for s in scores.values()])
    hi, el = np.quantile(all_scores, HIGH_Q), np.quantile(all_scores, ELEVATED_Q)

    clips = []
    for nid, s in sorted(scores.items(), key=lambda kv: int(kv[1]["rank"])):
        m = manifest[nid]
        score = float(s["score"])
        level = "high" if score >= hi else "elevated" if score >= el else "low"
        seg_out = []
        ego_cue_hit = False
        for r in sorted(segs[nid], key=lambda r: r["segment_number"]):
            p = parse(r["caption"])
            ego_cue_hit |= bool(p["cues"] & EGO_CUES)
            seg_out.append({"n": r["segment_number"], "of": r["total_segments"],
                            "risk": p["risk"], "cause": p["cause"], "ttc": p["ttc"], "lead": p["lead"],
                            "ego": p["ego"], "cues": sorted(p["cues"]), "summary": p["summary"]})
        cause = s["cause"]
        if cause == "none" and level != "low":
            cause = "ego" if ego_cue_hit else "other"
        y = yolo.get(nid, {})
        j = llm.get(nid, {})
        clips.append({
            "id": nid, "rider": rider_of(nid), "rank": int(s["rank"]), "score": round(score, 4), "level": level,
            "cause": cause, "cues": [c for c in s["cues"].split(";") if c], "summary": s["summary"],
            "peak_segment": int(s["peak_segment"]), "video": m["original_video"],
            "duration": float(m["chunk_duration_sec"]) if m["chunk_duration_sec"] else 5.0 * len(seg_out),
            "index_status": m["index_status"],
            "components": {k: round(float(s[f"{k}_z"]), 2) for k in ("precursor", "search", "yolo", "llm")
                           if s.get(f"{k}_z")},
            "llm": {"risk": j.get("llm_risk"), "cause": j.get("llm_cause"), "rationale": j.get("rationale")},
            "yolo": {k: round(float(y[k]), 3) for k in ("prox_last", "looming", "vru_in_path") if k in y},
            "segments": seg_out,
        })

    riders = defaultdict(list)
    for c in clips:
        riders[c["rider"]].append(c)
    rider_out = []
    for rid, cs in sorted(riders.items()):
        ego_high = sum(c["level"] == "high" and c["cause"] == "ego" for c in cs)
        ego_elev = sum(c["level"] == "elevated" and c["cause"] == "ego" for c in cs)
        other = sum(c["level"] != "low" and c["cause"] != "ego" for c in cs)
        rider_out.append({"id": rid, "trips": len(cs), "ego_high": ego_high, "ego_elevated": ego_elev,
                          "other_events": other, "clip_ids": [c["id"] for c in cs]})

    data = {
        "generated_from": "Nexar Collision Prediction public test (batch A, 2026-10-02 upload)",
        "model_notes": {"reasoner": "nvidia/cosmos3-nano-reasoner", "embedder": "nvidia/cosmos-embed1",
                        "detector": "yolo11s", "llm": "W&B Inference Qwen/Qwen3-30B-A3B-Instruct-2507"},
        "thresholds": {"high": round(float(hi), 4), "elevated": round(float(el), 4)},
        "segments_bucket": next(iter(segs.values()))[0]["source"].split("/")[2],
        "search_window": SEARCH_WINDOW,
        "policy": {"counts_toward_score": "ego-caused elevated/high events only", "tiers": [
            {"min": 85, "name": "Safe-driver reward", "action": "eligible for up to 15% discount after human review"},
            {"min": 70, "name": "Standard", "action": "no premium change"},
            {"min": 0, "name": "Coaching offered", "action": "free coaching; no premium increase"}]},
        "riders": rider_out, "clips": clips,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(clips)} clips, {len(rider_out)} simulated riders, "
          f"{OUT.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
