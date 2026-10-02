"""Uniform per-clip perception features for every batch-A clip (resumable).

For indexed segments it reuses what the pipeline stored (VastDB visual vectors, YOLO sidecars in S3);
for segments the index never wrote it calls the same Embed1 / YOLO11 models directly, so partially
indexed clips are not treated differently from complete ones.

Outputs (no labels):
  data/cache/visual_vectors.npz     source -> 256-d visual embedding (gitignored, large)
  results/yolo_features.csv         nexar_id, in-path proximity / looming / vulnerable-road-user features
"""
import base64
import csv
import gzip
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import vdb  # noqa: E402
from vss import s3_client  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
VEC_OUT = CACHE / "visual_vectors.npz"
YOLO_OUT = ROOT / "results" / "yolo_features.csv"
GPU = os.environ.get("GPU_HOST", "166.19.38.112")
HDR = {"Authorization": f"Bearer {os.environ['GPU_BEARER_TOKEN']}"}
ROAD_USERS = {"car", "truck", "bus", "motorcycle", "bicycle", "person"}
VRU = {"person", "bicycle", "motorcycle"}


def in_path(bbox, w, h):
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2
    return 0.3 * w <= cx <= 0.7 * w and y2 >= 0.5 * h


def path_features(frames, w=1280, h=720, fps=30.0):
    """Features over the final second of a segment's YOLO frames."""
    def frame_stats(fr):
        best, vru = 0.0, 0
        for d in fr.get("detections", []):
            if d["label"] not in ROAD_USERS or d.get("confidence", 0) < 0.4 or not in_path(d["bbox"], w, h):
                continue
            x1, y1, x2, y2 = d["bbox"]
            best = max(best, (x2 - x1) * (y2 - y1) / (w * h))
            vru += d["label"] in VRU
        return best, vru

    stats = [frame_stats(f) for f in frames]
    k = max(1, int(round(fps / 2)))
    last = stats[-k:]
    before = stats[-3 * k:-2 * k] or stats[:k]
    prox_last = max(s[0] for s in last)
    prox_before = max(s[0] for s in before)
    return {"prox_last": round(prox_last, 5),
            "looming": round(min(5.0, (prox_last + 1e-3) / (prox_before + 1e-3)), 4),
            "vru_in_path": max(s[1] for s in last)}


def main():
    s3, seg_bucket = s3_client(), os.environ["S3_SEGMENTS_BUCKET"]
    manifest = list(csv.DictReader(open(ROOT / "manifests/batch_a.csv")))
    rows = {r["source"]: r for r in vdb.fetch_segments([m["original_video"] for m in manifest])}
    CACHE.mkdir(parents=True, exist_ok=True)
    vectors = dict(np.load(VEC_OUT)) if VEC_OUT.exists() else {}

    segs = []
    for m in manifest:
        stem = m["original_video"].rsplit("/", 1)[1][:-4]
        keys = sorted(o["Key"] for o in s3.list_objects_v2(
            Bucket=seg_bucket, Prefix=f"segments/{stem}_segment_").get("Contents", []))
        segs += [(m["nexar_id"], k, k == keys[-1]) for k in keys]

    def video(key):
        return base64.b64encode(s3.get_object(Bucket=seg_bucket, Key=key)["Body"].read()).decode()

    def vec_job(item):
        nid, key, _ = item
        src = f"s3://{seg_bucket}/{key}"
        if src in vectors:
            return src, None
        if src in rows:
            return src, np.asarray(rows[src]["vectors_visual"], dtype=np.float32)
        r = httpx.post(f"http://{GPU}:8003/v1/embeddings", headers=HDR, timeout=120, json={
            "input": ["data:video/mp4;base64," + video(key)], "model": "nvidia/cosmos-embed1",
            "request_type": "query", "encoding_format": "float"})
        r.raise_for_status()
        v = np.asarray(r.json()["data"][0]["embedding"], dtype=np.float32)
        return src, v / np.linalg.norm(v)

    def yolo_job(item):
        nid, key, _ = item
        det_key = key.replace("segments/", "detections/", 1)[:-4] + ".json.gz"
        try:
            d = json.loads(gzip.decompress(s3.get_object(Bucket=seg_bucket, Key=det_key)["Body"].read()))
            source = "pipeline_sidecar"
        except s3.exceptions.NoSuchKey:
            r = httpx.post(f"http://{GPU}:8002/v1/infer", headers=HDR, timeout=180, json={
                "video_base64": video(key), "filename": key.rsplit("/", 1)[1], "include_frames": True})
            r.raise_for_status()
            d = r.json()
            source = "direct_yolo"
        fps = float(d.get("fps") or 30.0)
        return {"nexar_id": nid, "segment_key": key, "yolo_source": source, **path_features(d["frames"], fps=fps)}

    with ThreadPoolExecutor(4) as ex:
        for src, v in ex.map(vec_job, segs):
            if v is not None:
                vectors[src] = v
    np.savez_compressed(VEC_OUT, **vectors)
    direct = sum(1 for _, k, _ in segs if f"s3://{seg_bucket}/{k}" not in rows)
    print(f"visual vectors: {len(vectors)} segments ({direct} embedded directly)")

    last_segs = [s for s in segs if s[2]]
    with ThreadPoolExecutor(4) as ex:
        feats = list(ex.map(yolo_job, last_segs))
    with open(YOLO_OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(feats[0]))
        w.writeheader()
        w.writerows(sorted(feats, key=lambda r: r["nexar_id"]))
    n_direct = sum(r["yolo_source"] == "direct_yolo" for r in feats)
    print(f"yolo features: {len(feats)} clips ({n_direct} via direct YOLO) -> {YOLO_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
