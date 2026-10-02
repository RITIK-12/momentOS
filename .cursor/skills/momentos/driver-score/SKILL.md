---
name: driver-score
description: >-
  Turn clip-level risk into an opt-in, discount-only safe-driving score per driver with ego-fault
  attribution, contest and human review. Use when changing the driver score formula, tiers, the
  simulated-rider grouping, or the fairness policy shown in the MomentOS app.
---

# Driver safe-driving score

## Policy (do not weaken without the team's explicit decision)

1. Opt-in and driver-facing; the driver sees every counted moment with its clip and cues.
2. Only moments whose dominant cause is the **ego driver** count. Moments caused by other road
   users are shown as "not counted".
3. Tiers can only grant a discount or offer coaching. **No surcharge tier.**
4. Any tier change goes to human review; drivers can contest a moment, which removes it from the
   score until reviewed.
5. No location features and no identification of people or vehicles (Nexar license).

## Formula (`app/main.py::rider_summary`)

```
levels: high = top 20% clip scores, elevated = next 20%   (build_app_data.py)
rate   = (ego_high + 0.4 × ego_elevated) per 10 trips      (contested moments excluded)
score  = max(0, round(100 − 35 × rate))
tiers  = ≥85 Safe-driver reward (discount after review) · 70–84 Standard · <70 Coaching offered
```

Cause comes from the riskiest segment's `CAUSE`; if it says `none` on a flagged clip, ego cues
(`ego_speeding`, `ego_tailgating`, `ego_lane_drift`, `ego_red_light`) make it `ego`, otherwise `other`.

## Simulated riders

Nexar clips come from unrelated anonymous drivers. `build_app_data.py` groups them into 24 demo
"drivers" by hashing the clip id. Always label them as simulated; never imply real people.
