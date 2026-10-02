# 49

## Project
MomentOS scores dashcam trips for near-miss risk, attributes each moment to the driver or another road user, and turns only driver-caused moments into an opt-in safe-driving score that can unlock a discount or coaching — never a surcharge.

**Stack:** VAST DataEngine (Segmenter, YOLO11, Cosmos Reason, Cosmos Embed1, VastDB), VSS search / stream / synthesize, W&B Inference (Qwen3-30B), FastAPI app on Kubernetes via deploy-app-no-registry
**Code:** https://github.com/RITIK-12/momentOS
**Live app:** http://team-49-vss.thecosmoslabs.com/app
**Supplementary:** none

## Feedback
We called Cosmos Reason directly for the precursor captions because the shared pipeline had a large backlog and a full re-ingest of 667 clips would not have finished in time. `/search` with `top_k=100` OOM-killed the 4 GiB backend; keep it at 50 or below. Tags on our Nexar upload contain the labels, and re-ingest cannot clear them, so the app never reads tags.
