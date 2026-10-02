---
name: nexar-dataset
description: >-
  Map the Nexar Collision Prediction public-test clips uploaded to team-49's VSS index back to
  Nexar ids, keep labels out of the pipeline, and know the dataset's license limits. Use when
  building or refreshing manifests/batch_a.csv, locating a clip by Nexar id, or handling labels.
---

# Nexar dataset (MomentOS)

## What is indexed

- Nexar public test split: 667 dashcam clips (~10 s, 1280x720, 30 fps). 334 positives end
  0.5 / 1.0 / 1.5 s before a collision or near-miss (impact not visible); 333 negatives are normal driving.
- **Batch A** = the upload on 2026-10-02 between 19:40 and 20:20 UTC (811 objects, 667 unique ids,
  144 uploaded twice). MomentOS uses batch A only. Later uploads that day (test-private, train) and
  all 2026-10-01 videos are out of scope.
- Object keys are `team-49/<YYYYMMDD_HHMMSS>_<hash>.mp4` in `$S3_CHUNKS_BUCKET`; the Nexar file name
  survives only in S3 object metadata `original-filename` (e.g. `02634.mp4`).

## Build the manifest

```bash
.venv/bin/python scripts/build_manifest.py   # -> manifests/batch_a.csv
```

Selects batch A **by upload time, never by tags**, and picks the earliest fully indexed copy per id.
Columns: `nexar_id, original_video, upload_timestamp, index_status (full|pending), total_segments,
chunk_duration_sec, uploaded_copies`. No labels.

## Labels (offline only)

- `data/nexar/labels_public.csv` (`id,target,batch`) and the Nexar `metadata.csv` / `solution.csv`
  live in gitignored `data/`. The Hugging Face dataset is gated: accept its terms and download with
  your own login; never commit these files.
- Batch-A **tags in VastDB leak labels** (`near-collision` / `near-collison` / `miss`). Re-ingest cannot
  overwrite tags. Never read, filter on, display, or send `tags`.
- Never put labels in `camera_id`, `location`, prompts, or filenames sent to the pipeline.
- Do not use index completeness as a feature: all 77 initially pending clips were negatives.

## License guardrails (Nexar Open Data License)

Credit "Moura, Daniel C., and Zvitia, Orly. Nexar Collision Dataset. Hugging Face, 2025". No resale or
redistribution for profit; no re-identification of people or vehicles; no systems that cause harm or
unsafe driving; no deepfakes; no weapons; **no exploiting accident-prone regions or individuals for
predatory financial purposes such as unethical insurance practices** (hence MomentOS is opt-in,
discount/coaching-only, ego-fault-only, human-reviewed, and uses no location features).
