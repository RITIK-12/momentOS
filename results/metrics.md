# MomentOS evaluation: Nexar public test (batch A)

Clips scored: 667 (334 positive, 333 negative). Random-ranking AP = 0.501.

Blend weights (fixed a priori): precursor=0.4, llm=0.25, search=0.2, yolo=0.15.

## Overall

| Model | AP | ROC AUC |
|---|---|---|
| precursor | 0.715 | 0.770 |
| llm | 0.698 | 0.746 |
| search | 0.643 | 0.666 |
| yolo | 0.621 | 0.654 |
| **final blend** | 0.754 | 0.785 |

## Ablation (drop one component)

| Without | AP | ROC AUC |
|---|---|---|
| precursor | 0.735 | 0.767 |
| llm | 0.748 | 0.778 |
| search | 0.747 | 0.779 |
| yolo | 0.750 | 0.777 |

Structured-caption parse rate: 667/667 clips.

## Checks

- Like-for-like with `baseline_search.md` (the 590 clips fully indexed at the start, random AP 0.566): final blend AP 0.817, ROC AUC 0.796.
- Index-completeness bias: all 77 initially pending clips are negatives. Their mean score is 0.437 vs 0.416 for indexed negatives, so missing index rows do not make clips look safer.

Breakdowns by time_to_accident / weather / light / scene need the Nexar `test-public/{positive,negative}/metadata.csv` files in `data/nexar/` (gated on Hugging Face).
