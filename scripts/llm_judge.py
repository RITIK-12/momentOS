"""Optional W&B LLM rating per clip from its precursor captions (text only, resumable).

Writes results/llm_judge.jsonl: {nexar_id, llm_risk, llm_cause, rationale}. No labels involved.
"""
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vss  # noqa: E402,F401
from wandb_llm import DEFAULT_MODEL, chat_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CAPTIONS = ROOT / "results" / "precursor_captions.jsonl"
OUT = ROOT / "results" / "llm_judge.jsonl"

SYSTEM = (
    "You review dashcam analysis for a driver-facing road-safety coach. You get per-segment notes for one "
    "~10 s clip in time order; the clip ends right before the moment that matters. Estimate how likely a "
    "crash or near-miss is within ~1.5 s after the clip ends. Weight the final segment most. Decide who "
    "creates the danger: 'ego' (camera car's own driving), 'other' (another road user), or 'none'. "
    'Reply with JSON only: {"risk": <0-10 number>, "cause": "ego|other|none", "rationale": "<max 25 words>"}'
)


def main():
    by_id = defaultdict(list)
    for line in CAPTIONS.open():
        r = json.loads(line)
        by_id[r["nexar_id"]].append(r)
    done = {json.loads(l)["nexar_id"] for l in OUT.open()} if OUT.exists() else set()
    todo = sorted(set(by_id) - done)
    print(f"{len(done)} done, {len(todo)} to rate with {DEFAULT_MODEL}", flush=True)

    def rate(nid):
        segs = sorted(by_id[nid], key=lambda r: r["segment_number"])
        notes = "\n\n".join(f"Segment {s['segment_number']}/{s['total_segments']}:\n{s['caption']}" for s in segs)
        j = chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": notes}])
        return {"nexar_id": nid, "llm_risk": j.get("risk"), "llm_cause": j.get("cause"),
                "rationale": j.get("rationale"), "model": DEFAULT_MODEL}

    with ThreadPoolExecutor(8) as ex, OUT.open("a") as f:
        for k, rec in enumerate(ex.map(rate, todo), 1):
            f.write(json.dumps(rec) + "\n")
            if k % 100 == 0:
                print(f"{k}/{len(todo)}", flush=True)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
