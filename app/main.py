"""MomentOS: opt-in safe-driver scoring from dashcam near-miss analysis.

Serves the web UI and a thin API over precomputed clip scores (static/data.json) and the team's
VSS backend (search, playback, synthesis). VSS credentials stay server-side; the browser never sees
a VSS token. Only batch-A clips listed in data.json can be streamed or searched.
"""
import asyncio
import json
import os
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
STATIC = HERE / "static"
DATA = json.loads((STATIC / "data.json").read_text())
CLIPS = {c["id"]: c for c in DATA["clips"]}
for _c in CLIPS.values():
    _stem = _c["video"].rsplit("/", 1)[1][:-4]
    for _s in _c["segments"]:
        _s["src"] = f"s3://{DATA['segments_bucket']}/segments/{_stem}_segment_{_s['n']:03d}_of_{_s['of']:03d}.mp4"
BY_VIDEO = {c["video"]: c["id"] for c in CLIPS.values()}
ALLOWED_SOURCES = {c["video"] for c in CLIPS.values()} | {s["src"] for c in CLIPS.values() for s in c["segments"]}
RIDERS = {r["id"]: r for r in DATA["riders"]}

VSS_URL = os.environ.get("VSS_URL", "").rstrip("/")
WANDB_MODEL = os.environ.get("WANDB_MODEL", "Qwen/Qwen3-30B-A3B-Instruct-2507")

CONTESTED: dict[str, dict] = {}
REPORTS: dict[str, dict] = {}
COACH: dict[str, dict] = {}

app = FastAPI(title="MomentOS")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class VSSClient:
    def __init__(self):
        self.token, self.lock = None, asyncio.Lock()
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15))

    async def login(self):
        r = await self.http.post(f"{VSS_URL}/api/v1/auth/login", json={
            "username": os.environ["VSS_USERNAME"], "password": os.environ["VSS_PASSWORD"]})
        r.raise_for_status()
        self.token = r.json()["access_token"]

    async def ensure(self):
        async with self.lock:
            if not self.token:
                await self.login()

    async def request(self, method, path, **kw):
        await self.ensure()
        for attempt in range(2):
            r = await self.http.request(method, f"{VSS_URL}/api/v1{path}",
                                        headers={"Authorization": f"Bearer {self.token}"}, **kw)
            if r.status_code == 401 and attempt == 0:
                await self.login()
                continue
            return r


vss = VSSClient()


def rider_summary(r):
    clips = [CLIPS[i] for i in r["clip_ids"]]
    counted = [c for c in clips if c["cause"] == "ego" and c["level"] != "low" and c["id"] not in CONTESTED]
    ego_high = sum(c["level"] == "high" for c in counted)
    ego_elev = sum(c["level"] == "elevated" for c in counted)
    rate = (ego_high + 0.4 * ego_elev) / max(1, len(clips)) * 10
    score = max(0, round(100 - 35 * rate))
    tier = next(t for t in DATA["policy"]["tiers"] if score >= t["min"])
    return {"id": r["id"], "trips": len(clips), "safe_score": score, "tier": tier,
            "ego_high": ego_high, "ego_elevated": ego_elev,
            "other_events": sum(c["level"] != "low" and c["cause"] != "ego" for c in clips),
            "contested": sum(c["id"] in CONTESTED for c in clips),
            "events_per_10_trips": round(rate, 2)}


def clip_card(c):
    return {k: c[k] for k in ("id", "rider", "rank", "score", "level", "cause", "cues", "summary",
                              "peak_segment", "duration", "index_status")} | {"contested": c["id"] in CONTESTED}


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health():
    return {"ok": True, "clips": len(CLIPS), "riders": len(RIDERS)}


@app.get("/api/overview")
async def overview():
    riders = sorted((rider_summary(r) for r in RIDERS.values()), key=lambda r: -r["safe_score"])
    levels = {lvl: sum(c["level"] == lvl for c in CLIPS.values()) for lvl in ("high", "elevated", "low")}
    causes = {k: sum(c["cause"] == k and c["level"] != "low" for c in CLIPS.values()) for k in ("ego", "other", "none")}
    return {"riders": riders, "levels": levels, "flagged_by_cause": causes, "policy": DATA["policy"],
            "models": DATA["model_notes"], "source": DATA["generated_from"], "clips": len(CLIPS)}


@app.get("/api/riders/{rid}")
async def rider(rid: str):
    if rid not in RIDERS:
        raise HTTPException(404, "unknown rider")
    r = RIDERS[rid]
    clips = sorted((CLIPS[i] for i in r["clip_ids"]), key=lambda c: -c["score"])
    return {"summary": rider_summary(r), "clips": [clip_card(c) for c in clips], "coach": COACH.get(rid)}


@app.get("/api/clips")
async def clips(level: str = "", cause: str = "", limit: int = 100, offset: int = 0):
    cs = sorted(CLIPS.values(), key=lambda c: c["rank"])
    if level:
        cs = [c for c in cs if c["level"] == level]
    if cause:
        cs = [c for c in cs if c["cause"] == cause]
    return {"total": len(cs), "clips": [clip_card(c) for c in cs[offset:offset + min(limit, 200)]]}


@app.get("/api/clips/{cid}")
async def clip(cid: str):
    c = CLIPS.get(cid)
    if not c:
        raise HTTPException(404, "unknown clip")
    return c | {"contested": CONTESTED.get(cid), "report": REPORTS.get(cid)}


@app.get("/api/stream/{cid}")
async def stream(cid: str, request: Request, seg: int = 0):
    c = CLIPS.get(cid)
    if not c:
        raise HTTPException(404, "unknown clip")
    source = c["video"] if seg == 0 else next((s["src"] for s in c["segments"] if s["n"] == seg), None)
    if source not in ALLOWED_SOURCES:
        raise HTTPException(404, "unknown segment")
    await vss.ensure()
    headers = {"Range": request.headers["range"]} if "range" in request.headers else {}
    req = vss.http.build_request("GET", f"{VSS_URL}/api/v1/videos/stream",
                                 params={"source": source, "token": vss.token}, headers=headers)
    upstream = await vss.http.send(req, stream=True)
    if upstream.status_code == 401:
        await upstream.aclose()
        await vss.login()
        req = vss.http.build_request("GET", f"{VSS_URL}/api/v1/videos/stream",
                                     params={"source": source, "token": vss.token}, headers=headers)
        upstream = await vss.http.send(req, stream=True)
    out_headers = {k: upstream.headers[k] for k in ("content-length", "content-range", "accept-ranges")
                   if k in upstream.headers}
    out_headers["cache-control"] = "private, max-age=600"

    async def body():
        try:
            async for chunk in upstream.aiter_bytes(64 * 1024):
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(body(), status_code=upstream.status_code, media_type="video/mp4", headers=out_headers)


REPORT_PROMPT = (
    "Role: road-safety reviewer writing a driver-facing incident note from dashcam evidence only.\n"
    "Output markdown with exactly these sections:\n"
    "**What happened** - 2 sentences, chronological, end with the moment of highest risk.\n"
    "**Contributing factors** - up to 4 bullets; tag each (ego driver) or (other road user).\n"
    "**What the driver could do differently** - 1-2 coaching bullets, or 'Nothing: the risk came from another road user.'\n"
    "**Confidence** - one sentence on evidence quality.\n"
    "Rules: use only the evidence; no filenames; never identify people, faces or plates; no blame beyond the evidence; "
    "under 170 words."
)


@app.post("/api/clips/{cid}/report")
async def report(cid: str):
    c = CLIPS.get(cid)
    if not c:
        raise HTTPException(404, "unknown clip")
    if cid in REPORTS:
        return REPORTS[cid]
    notes = "; ".join(f"segment {s['n']}: risk {s['risk']}, cause {s['cause']}, cues {', '.join(s['cues']) or 'none'}"
                      f" - {s['summary']}" for s in c["segments"])
    body = {"original_video": c["video"], "max_segments": 10, "system_prompt": REPORT_PROMPT,
            "question": f"Write the incident note for this dashcam clip. Structured precursor analysis: {notes}"}
    r = await vss.request("POST", "/videos/synthesize", json=body)
    if r.status_code != 200:
        raise HTTPException(502, f"synthesize failed ({r.status_code})")
    j = r.json()
    REPORTS[cid] = {"answer": j.get("answer") or (j.get("llm_synthesis") or {}).get("response", ""),
                    "segments_used": j.get("segments_used") or j.get("segment_count"), "generated_at": time.time()}
    return REPORTS[cid]


@app.post("/api/clips/{cid}/contest")
async def contest(cid: str, request: Request):
    if cid not in CLIPS:
        raise HTTPException(404, "unknown clip")
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    if body.get("withdraw"):
        CONTESTED.pop(cid, None)
    else:
        CONTESTED[cid] = {"reason": str(body.get("reason", ""))[:300], "at": time.time(), "status": "pending human review"}
    return {"contested": CONTESTED.get(cid), "rider": rider_summary(RIDERS[CLIPS[cid]["rider"]])}


@app.post("/api/riders/{rid}/coach")
async def coach(rid: str):
    if rid not in RIDERS:
        raise HTTPException(404, "unknown rider")
    if rid in COACH:
        return COACH[rid]
    s = rider_summary(RIDERS[rid])
    events = [CLIPS[i] for i in RIDERS[rid]["clip_ids"] if CLIPS[i]["level"] != "low"]
    lines = [f"- {c['level']} risk, caused by {c['cause']}; cues: {', '.join(c['cues']) or 'none'}; {c['summary']}"
             for c in sorted(events, key=lambda c: -c["score"])[:8]]
    prompt = (f"Driver safe-driving score {s['safe_score']}/100 over {s['trips']} trips ({s['tier']['name']}). "
              f"Flagged moments:\n" + ("\n".join(lines) or "- none") +
              "\n\nWrite a short, encouraging coaching note for this driver (max 90 words): one thing they do well, "
              "up to two concrete habits to improve based ONLY on ego-caused moments, and note that moments caused "
              "by other road users do not affect their score. Do not mention premiums increasing.")
    key, team, project = (os.environ.get(k) for k in ("WANDB_API_KEY", "WANDB_TEAM", "WANDB_PROJECT"))
    if not key:
        raise HTTPException(503, "W&B inference not configured")
    async with httpx.AsyncClient(timeout=60) as h:
        r = await h.post("https://api.inference.wandb.ai/v1/chat/completions",
                         headers={"Authorization": f"Bearer {key}", "OpenAI-Project": f"{team}/{project}"},
                         json={"model": WANDB_MODEL, "max_tokens": 220, "temperature": 0.3,
                               "messages": [{"role": "user", "content": prompt}]})
    if r.status_code != 200:
        raise HTTPException(502, f"W&B inference failed ({r.status_code})")
    COACH[rid] = {"note": r.json()["choices"][0]["message"]["content"], "model": WANDB_MODEL}
    return COACH[rid]


@app.get("/api/search")
async def search(q: str):
    q = q.strip()[:200]
    if not q:
        return {"results": []}
    start, end = DATA["search_window"]
    r = await vss.request("POST", "/search", json={
        "query": q, "top_k": 40, "llm_top_n": 1, "min_similarity": 0.1, "time_filter": "custom",
        "custom_start_date": start, "custom_end_date": end})
    if r.status_code != 200:
        raise HTTPException(502, f"search failed ({r.status_code})")
    seen, out = set(), []
    for hit in r.json().get("results", []):
        cid = BY_VIDEO.get(hit.get("original_video"))
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append(clip_card(CLIPS[cid]) | {"similarity": round(hit.get("similarity_score", 0), 3),
                                             "match_segment": hit.get("segment_number"),
                                             "match_start": hit.get("segment_start_sec")})
    return {"results": out}


@app.exception_handler(httpx.HTTPError)
async def upstream_error(_, exc):
    return JSONResponse({"detail": f"upstream error: {type(exc).__name__}"}, status_code=502)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), proxy_headers=True)
