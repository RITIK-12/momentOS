# Baseline: hazard-query similarity on default captions

590 fully indexed batch-A clips (334 positive).

Random ranking AP = 0.566, AUC = 0.500.

| Query | Signal | AP | ROC AUC | Positives in top 50 |
|---|---|---|---|---|
| vehicle ahead braking suddenly | text_max | 0.627 | 0.584 | 34/50 |
| vehicle ahead braking suddenly | visual_max | 0.660 | 0.642 | 30/50 |
| vehicle ahead braking suddenly | hybrid_max | 0.650 | 0.628 | 35/50 |
| vehicle ahead braking suddenly | text_last | 0.623 | 0.582 | 33/50 |
| vehicle ahead braking suddenly | visual_last | 0.674 | 0.663 | 34/50 |
| car cutting into our lane | text_max | 0.676 | 0.630 | 34/50 |
| car cutting into our lane | visual_max | 0.626 | 0.612 | 27/50 |
| car cutting into our lane | hybrid_max | 0.659 | 0.641 | 33/50 |
| car cutting into our lane | text_last | 0.678 | 0.636 | 36/50 |
| car cutting into our lane | visual_last | 0.636 | 0.625 | 29/50 |
| pedestrian stepping into the road | text_max | 0.533 | 0.433 | 25/50 |
| pedestrian stepping into the road | visual_max | 0.608 | 0.499 | 37/50 |
| pedestrian stepping into the road | hybrid_max | 0.566 | 0.457 | 32/50 |
| pedestrian stepping into the road | text_last | 0.517 | 0.416 | 25/50 |
| pedestrian stepping into the road | visual_last | 0.595 | 0.507 | 30/50 |
| all three (z-scored hybrid sum) | hybrid_max | 0.689 | 0.651 | 39/50 |
