"""Step 5 probe: run a candidate ingestion prompt directly on Cosmos Reason for a few clips.

Reads segment videos from S3 and calls the reasoner; writes nothing to the index.
Use it to iterate on the prompt before spending a re-ingest.

  python scripts/prompt_probe.py prompts/precursor_v1.txt --pos 5 --neg 5
"""
import argparse
import base64
import csv
import json
import os
import random
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vdb  # noqa: E402
from risk_parse import parse  # noqa: E402
from vss import s3_client  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REASON_URL = os.environ.get("REASON_URL", "http://166.19.38.112:8001")
MODEL = "nvidia/cosmos3-nano-reasoner"


def reason(prompt, video_bytes, max_tokens=400):
    content = [{"type": "text", "text": prompt},
               {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + base64.b64encode(video_bytes).decode()}}]
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": content}],
                       "max_tokens": max_tokens, "temperature": 0.2}).encode()
    req = urllib.request.Request(f"{REASON_URL}/v1/chat/completions", data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {os.environ['GPU_BEARER_TOKEN']}"})
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=180))["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code not in (429, 502, 503, 504) or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--pos", type=int, default=5)
    ap.add_argument("--neg", type=int, default=5)
    ap.add_argument("--seed", type=int, default=49)
    ap.add_argument("--ids", default="", help="comma list of Nexar ids (overrides random pick)")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    prompt = Path(args.prompt).read_text().strip()
    assert len(prompt) <= 800, f"prompt is {len(prompt)} chars (max 800)"

    labels = {r["id"]: int(r["target"]) for r in csv.DictReader(open(ROOT / "data/nexar/labels_public.csv"))}
    man = {r["nexar_id"]: r for r in csv.DictReader(open(ROOT / "manifests/batch_a.csv")) if r["index_status"] == "full"}
    if args.ids:
        ids = args.ids.split(",")
    else:
        rnd = random.Random(args.seed)
        ids = (rnd.sample(sorted(i for i in man if labels[i] == 1), args.pos)
               + rnd.sample(sorted(i for i in man if labels[i] == 0), args.neg))

    rows = vdb.fetch_segments([man[i]["original_video"] for i in ids], with_vectors=False)
    old = {(r["original_video"], r["segment_number"]): r for r in rows}
    s3, seg_bucket = s3_client(), os.environ["S3_SEGMENTS_BUCKET"]

    jobs = []
    for i in ids:
        for (ov, n), r in sorted(old.items()):
            if ov == man[i]["original_video"]:
                jobs.append((i, n, r["total_segments"], r["source"], r["reasoning_content"]))

    def run(job):
        i, n, total, source, old_caption = job
        key = source.split(f"s3://{seg_bucket}/", 1)[1]
        video = s3.get_object(Bucket=seg_bucket, Key=key)["Body"].read()
        t = time.time()
        new_caption = reason(prompt, video)
        return {"id": i, "label": labels[i], "segment": n, "total_segments": total,
                "seconds": round(time.time() - t, 1), "old": old_caption, "new": new_caption}

    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(run, jobs))

    out = Path(args.out or f"/tmp/m49_probe_{Path(args.prompt).stem}.json")
    out.write_text(json.dumps(results, indent=1))
    for r in results:
        p = parse(r["new"])
        print(f"\n### {r['id']} {'POS' if r['label'] else 'NEG'} seg {r['segment']}/{r['total_segments']} "
              f"({r['seconds']}s) risk={p['risk']} cause={p['cause']} ttc={p['ttc']} cues={sorted(p['cues'])}")
        print(r["new"])
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
