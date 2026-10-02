"""Re-ingest batch-A clips through the VSS pipeline with the precursor prompt.

Follows the reingest-videos skill: one POST /dashboard/reingest per complete parent video
(chunk_count=1), custom_prompt from prompts/, and label-free metadata overrides
(camera_id = Nexar id, location = nexar, capture_type = traffic). Tags cannot be overridden
by the API and are never read here.

Dry run by default; pass --go to submit. Progress is logged to results/reingest_log.jsonl.

  python scripts/reingest_batch.py prompts/precursor_v1.txt --ids 00230,01675 [--go]
  python scripts/reingest_batch.py prompts/precursor_v1.txt --batch 1 --size 100 [--go]
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vss import VSS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "results" / "reingest_log.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--ids", default="")
    ap.add_argument("--batch", type=int, default=0, help="1-based batch over manifest order")
    ap.add_argument("--size", type=int, default=100)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--wait", action="store_true", help="poll jobs until completed")
    args = ap.parse_args()
    prompt = Path(args.prompt).read_text().strip()
    assert len(prompt) <= 800

    manifest = [r for r in csv.DictReader(open(ROOT / "manifests/batch_a.csv"))]
    done = set()
    if LOG.exists():
        done = {json.loads(l)["nexar_id"] for l in LOG.open() if json.loads(l).get("prompt") == Path(args.prompt).stem}
    if args.ids:
        wanted = set(args.ids.split(","))
        targets = [m for m in manifest if m["nexar_id"] in wanted]
    else:
        targets = manifest[(args.batch - 1) * args.size: args.batch * args.size]
    skipped = [m["nexar_id"] for m in targets if m["index_status"] != "full"]
    targets = [m for m in targets if m["index_status"] == "full" and m["nexar_id"] not in done]
    print(f"{len(targets)} clips to re-ingest; skipped (not fully indexed, re-ingest API needs complete chunks): {skipped}")
    if not args.go:
        print("dry run; add --go to submit")
        return

    v = VSS()
    jobs = []
    LOG.parent.mkdir(exist_ok=True)
    for m in targets:
        body = {"original_video": m["original_video"], "chunk_count": 1, "custom_prompt": prompt,
                "camera_id": m["nexar_id"], "location": "nexar", "capture_type": "traffic"}
        r = v.post("/dashboard/reingest", body)
        rec = {"nexar_id": m["nexar_id"], "original_video": m["original_video"], "job_id": r.get("job_id"),
               "copied_segments": r.get("copied_segments"), "prompt": Path(args.prompt).stem, "at": time.time()}
        jobs.append(rec)
        with LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        time.sleep(0.5)
    print(f"submitted {len(jobs)} jobs")

    while args.wait and jobs:
        time.sleep(15)
        pending = []
        for j in jobs:
            try:
                s = v.get(f"/dashboard/reingest/{j['job_id']}")
            except RuntimeError as e:
                print(f"{j['nexar_id']}: status unavailable ({str(e)[:80]})")
                continue
            if s.get("status") != "completed":
                pending.append(j)
        print(f"{len(jobs) - len(pending)}/{len(jobs)} completed", flush=True)
        jobs = pending


if __name__ == "__main__":
    main()
