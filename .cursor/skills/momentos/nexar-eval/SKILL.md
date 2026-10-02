---
name: nexar-eval
description: >-
  Evaluate MomentOS clip scores against Nexar public-test ground truth: AP / ROC AUC, ablations, and
  breakdowns by time_to_accident, weather, light and scene, plus the official evaluate_submission.py
  when available. Use when reporting accuracy or checking a scoring change.
---

# Nexar evaluation

```bash
.venv/bin/python scripts/score.py      # writes results/metrics.md
.venv/bin/python scripts/baseline_search.py   # step-4 baseline: hazard queries only
```

## Inputs (gitignored `data/nexar/`)

- `labels_public.csv` (`id,target,batch`): required.
- `test-public/{positive,negative}/metadata.csv`: enables the time_to_accident (0.5/1.0/1.5 s),
  weather, light_conditions and scene breakdowns. The time_to_accident table reports AP of each
  horizon's positives vs all negatives and their mean (mAP).
- `solution.csv` + `evaluate_submission.py`: if both exist, `score.py` runs the official script on
  `results/submission_public.csv`. Report the **Public** number only; the Private split is not on the
  VM and missing ids score 0.

## Rules

- Labels are used only here, offline. Never feed them back into prompts, metadata, or the app.
- Random-ranking AP equals the positive rate (0.50 on all 667; 0.566 on the 590 initially indexed).
- Compare against `results/baseline_search.md` (default captions + hazard search only).
