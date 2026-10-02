"""Direct VastDB reads and Cosmos-Embed1 query embeddings (read-only)."""
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np
import vastdb

sys.path.insert(0, str(Path(__file__).parent))
import vss  # noqa: E402,F401  (loads /config/<team>.config into the environment)

logging.getLogger("vastdb").setLevel(logging.ERROR)

VDB_ENDPOINT = os.environ.get("VDB_ENDPOINT", "http://builder-qe.cosmos-var201.cosmo.vastdata.com")
EMBED_URL = os.environ.get("EMBED_URL", "http://166.19.38.112:8003")
META_COLS = ["source", "original_video", "segment_number", "total_segments", "segment_start_sec",
             "segment_end_sec", "duration", "reasoning_content", "object_counts", "max_detection_conf",
             "detection_count", "upload_timestamp"]


def _table(tx):
    return (tx.bucket(os.environ["VASTDB_BUCKET"]).schema(os.environ["VDB_SCHEMA"])
            .table(os.environ["VDB_COLLECTION"]))


def fetch_segments(original_videos, with_vectors=True):
    """All segment rows whose original_video is in the given set."""
    wanted = set(original_videos)
    cols = META_COLS + (["vectors", "vectors_visual"] if with_vectors else [])
    session = vastdb.connect(endpoint=VDB_ENDPOINT, access=os.environ["ACCESS_KEY"],
                             secret=os.environ["SECRET_KEY"], ssl_verify=False)
    with session.transaction() as tx:
        t = _table(tx)
        rows = []
        for batch in t.select(columns=cols, predicate=t["original_video"].isin(sorted(wanted))):
            rows += batch.to_pylist()
    return rows


def embed_text(texts):
    """Cosmos-Embed1 text embeddings (L2-normalised), same space as the indexed vectors.

    The NIM rejects multi-item batches (422), so texts are sent one per request.
    """
    out = []
    for text in texts:
        body = json.dumps({"input": [text], "model": "nvidia/cosmos-embed1",
                           "request_type": "query", "encoding_format": "float"}).encode()
        req = urllib.request.Request(f"{EMBED_URL}/v1/embeddings", data=body, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {os.environ['GPU_BEARER_TOKEN']}"})
        out.append(json.load(urllib.request.urlopen(req, timeout=60))["data"][0]["embedding"])
    v = np.array(out, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)
