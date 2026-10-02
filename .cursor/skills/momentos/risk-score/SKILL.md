---
name: risk-score
description: >-
  Produce the MomentOS per-clip collision-risk score from Cosmos Reason precursor captions, W&B LLM
  judge, Cosmos Embed hazard-query similarity and YOLO in-path features, and write the id,score
  submission. Use when recomputing scores, changing components or weights, or explaining a score.
---

# Risk score

## Pipeline (run in order; each step is resumable)

```bash
.venv/bin/python scripts/precursor_run.py prompts/precursor_v1.txt   # Cosmos Reason on every segment from S3
.venv/bin/python scripts/fill_features.py                            # visual vectors + YOLO in-path features
.venv/bin/python scripts/llm_judge.py                                # W&B LLM judge per clip
.venv/bin/python scripts/score.py                                    # blend + evaluation
.venv/bin/python scripts/build_app_data.py                           # app/static/data.json
```

## Components (z-scored over clips, then blended)

| Component | Weight | Signal |
|---|---|---|
| precursor | 0.40 | 0.65 × last-segment RISK + 0.35 × max RISK, +0.5 if a strong cue in the last segment, +0.5 if TTC ≤ 2 s |
| llm | 0.25 | W&B LLM risk from the segment captions |
| search | 0.20 | Cosmos-Embed1 similarity of 3 hazard queries to segment **visual** vectors, last-segment weighted |
| yolo | 0.15 | largest in-path road user in the final 0.5 s, looming ratio, pedestrians/cyclists in path |

- Weights are fixed a priori. Do not tune them on the public labels; report ablations instead.
- Every clip gets every component the same way: segments missing from VastDB are embedded directly
  (same model, cosine 1.0 vs stored), and YOLO features come from the pipeline's detection sidecars.
- Caption-text vectors are excluded because they are missing for partly indexed clips.

## Outputs

`results/clip_scores.csv` (score, rank, components, dominant cause, cues, summary),
`results/submission_public.csv` (`id,score`, sample_submission format), `results/metrics.md`.
