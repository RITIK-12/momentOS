"""Build the batch-A manifest: Nexar id -> canonical indexed upload.

Batch A is the Nexar public-test upload done on 2026-10-02 between 19:40 and 20:20 UTC.
It is selected by upload time only; tags are never read because they carry labels.
For ids uploaded more than once, the earliest fully indexed copy is canonical; ids with
no fully indexed copy keep their latest upload with index_status=pending.

Output (no labels): manifests/batch_a.csv
"""
import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vss import VSS, s3_client  # noqa: E402

WINDOW = ("2026-10-02T19:40:00", "2026-10-02T20:20:00")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "manifests" / "batch_a.csv"


def main():
    s3, bucket = s3_client(), os.environ["S3_CHUNKS_BUCKET"]
    keys = [o["Key"]
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="team-49/20261002_")
            for o in page.get("Contents", [])]

    def head(key):
        md = s3.head_object(Bucket=bucket, Key=key)["Metadata"]
        return {"key": key, "original_filename": md.get("original-filename", ""),
                "upload_timestamp": md.get("upload-timestamp", "")}

    with ThreadPoolExecutor(32) as ex:
        objs = [o for o in ex.map(head, keys) if WINDOW[0] <= o["upload_timestamp"] < WINDOW[1]]

    indexed = {c["original_video"]: c for c in VSS().explore_all(date="2026-10-02")}

    by_id = {}
    for o in sorted(objs, key=lambda o: o["upload_timestamp"]):
        nexar_id = Path(o["original_filename"]).stem
        if not nexar_id.isdigit():
            print(f"skip non-Nexar filename: {o['key']}")
            continue
        entry = by_id.setdefault(nexar_id, {"copies": 0, "canonical": None, "latest": None})
        entry["copies"] += 1
        uri = f"s3://{bucket}/{o['key']}"
        entry["latest"] = (uri, o["upload_timestamp"])
        if entry["canonical"] is None and uri in indexed:
            entry["canonical"] = (uri, o["upload_timestamp"], indexed[uri])

    OUT.parent.mkdir(exist_ok=True)
    missing = []
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["nexar_id", "original_video", "upload_timestamp", "index_status", "total_segments",
                    "chunk_duration_sec", "uploaded_copies"])
        for nexar_id in sorted(by_id):
            e = by_id[nexar_id]
            if e["canonical"] is None:
                missing.append(nexar_id)
                uri, ts = e["latest"]
                w.writerow([nexar_id, uri, ts, "pending", "", "", e["copies"]])
                continue
            uri, ts, chunk = e["canonical"]
            w.writerow([nexar_id, uri, ts, "full", chunk.get("total_segments"),
                        chunk.get("chunk_duration_sec"), e["copies"]])

    n_dupe = sum(e["copies"] > 1 for e in by_id.values())
    print(f"batch-A objects in window: {len(objs)}")
    print(f"unique Nexar ids: {len(by_id)} (uploaded more than once: {n_dupe})")
    print(f"fully indexed: {len(by_id) - len(missing)}; pending: {len(missing)}")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
