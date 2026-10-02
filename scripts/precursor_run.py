"""Run the precursor prompt on every batch-A segment straight from S3 (resumable).

This is the offline equivalent of re-ingesting with the custom prompt: same model, same
segment files, but results go to results/precursor_captions.jsonl instead of VastDB.
It covers clips the index has not finished writing. Output carries no labels.

  python scripts/precursor_run.py prompts/precursor_v1.txt [--workers 4] [--limit N]
"""
import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import csv

sys.path.insert(0, str(Path(__file__).parent))
from prompt_probe import MODEL, reason  # noqa: E402
from vss import s3_client  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "precursor_captions.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    prompt_path = Path(args.prompt)
    prompt = prompt_path.read_text().strip()
    version = prompt_path.stem

    s3, seg_bucket = s3_client(), os.environ["S3_SEGMENTS_BUCKET"]
    manifest = list(csv.DictReader(open(ROOT / "manifests/batch_a.csv")))

    done = set()
    if OUT.exists():
        for line in OUT.open():
            r = json.loads(line)
            if r["prompt_version"] == version:
                done.add(r["source"])

    jobs = []
    for m in manifest:
        stem = m["original_video"].rsplit("/", 1)[1][:-4]
        keys = sorted(o["Key"] for o in s3.list_objects_v2(
            Bucket=seg_bucket, Prefix=f"segments/{stem}_segment_").get("Contents", []))
        for key in keys:
            source = f"s3://{seg_bucket}/{key}"
            if source in done:
                continue
            n, total = key[:-4].rsplit("_segment_", 1)[1].split("_of_")
            jobs.append({"nexar_id": m["nexar_id"], "original_video": m["original_video"], "source": source,
                         "key": key, "segment_number": int(n), "total_segments": int(total)})
    if args.limit:
        jobs = jobs[:args.limit]
    print(f"{len(done)} segments already done, {len(jobs)} to run", flush=True)

    lock = threading.Lock()
    OUT.parent.mkdir(exist_ok=True)

    def run(job):
        video = s3.get_object(Bucket=seg_bucket, Key=job["key"])["Body"].read()
        caption = reason(prompt, video)
        rec = {k: job[k] for k in ("nexar_id", "original_video", "source", "segment_number", "total_segments")}
        rec.update(caption=caption, model=MODEL, prompt_version=version)
        with lock, OUT.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    failed = 0
    with ThreadPoolExecutor(args.workers) as ex:
        futures = [ex.submit(run, j) for j in jobs]
        for k, fut in enumerate(as_completed(futures), 1):
            try:
                fut.result()
            except Exception as e:  # keep going; rerun picks up failures
                failed += 1
                print(f"failed: {str(e)[:160]}", flush=True)
            if k % 50 == 0:
                print(f"{k}/{len(jobs)} done ({failed} failed)", flush=True)
    print(f"finished: {len(jobs) - failed} ok, {failed} failed -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
