---
name: nexar-batch-ingest
description: >-
  Re-ingest batch-A Nexar clips through team-49's shared VSS pipeline with the MomentOS precursor
  prompt, in small batches, with label-free metadata, while watching pipeline backlog. Use when the
  user asks to re-ingest Nexar clips, refresh captions with a new prompt, or check re-ingest progress.
---

# Nexar batch re-ingest

Wraps `ingest/reingest-videos` (read it first) for many single-video targets.

## Rules

- The team shares one pipeline. **Ask before any re-ingest**; first run ≤10 clips, compare captions,
  then go batch by batch (≤100 clips) with the user's OK.
- Check backlog before each batch: `GET /api/v1/dashboard/stats` → `pipeline_alignment.pending_index`.
  If thousands of segments are pending, a batch will wait behind them; say so.
- Only fully indexed clips can be re-ingested (`index_status=full` in `manifests/batch_a.csv`). Clips
  with missing segments must be uploaded again or scored from S3 directly (`scripts/precursor_run.py`).
- Overrides sent: `custom_prompt` (≤800 chars), `camera_id=<nexar id>`, `location=nexar`,
  `capture_type=traffic`. Never labels. Tags are not overridable and stay leaky; ignore them.

## Commands

```bash
.venv/bin/python scripts/reingest_batch.py prompts/precursor_v1.txt --ids 00230,01675          # dry run
.venv/bin/python scripts/reingest_batch.py prompts/precursor_v1.txt --ids 00230,01675 --go --wait
.venv/bin/python scripts/reingest_batch.py prompts/precursor_v1.txt --batch 1 --size 100 --go
```

Jobs are logged to `results/reingest_log.jsonl`; poll `GET /api/v1/dashboard/reingest/<job_id>`.
A 404 after a backend restart only means the in-memory progress record was lost.

## Troubleshooting seen on build day

- Rows stop growing while segments pile up: check the VastDB writer pod logs; a replaced writer pod
  received no events for ~25 min, then recovered without intervention.
- Backend restarts (exit 137) under heavy `/search` with `top_k=100`: keep `top_k ≤ 50`.
