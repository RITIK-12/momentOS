# MomentOS

Opt-in safe-driver scoring from dashcam footage. Each trip gets a near-miss risk, a cause (the driver or another road user), and the cues behind it. Only moments the driver caused change the score. The score can qualify a driver for a discount or coaching. Tiers change only after human review, and a driver can contest any moment.

Live app: http://team-49-vss.thecosmoslabs.com/app

The drivers in the demo are simulated groups of anonymous Nexar clips, not real people. No location features are used. See [NOTICE.md](NOTICE.md).

## Scoring

Clips are about 10 seconds and stop before impact. The VAST pipeline cuts them into 5-second segments (YOLO11, Cosmos Reason, Cosmos Embed1, VastDB). Cosmos Reason answers `prompts/precursor_v1.txt` in a fixed form: `RISK`, `CAUSE`, `TTC`, `LEAD`, `EGO`, `CUES`, `SUMMARY`.

The clip score blends four signals. Weights were fixed before evaluation, with more weight on the last segment:

| Signal | Weight |
|---|---|
| Precursor risk from Cosmos Reason | 0.40 |
| W&B LLM judge on those captions | 0.25 |
| Cosmos Embed similarity to hazard queries | 0.20 |
| YOLO11 in-path proximity in the final 0.5 s | 0.15 |

## Results

Nexar public test, 667 clips (334 near-miss lead-ups, 333 normal driving). A random ranking scores AP 0.501.

| Model | AP | ROC AUC |
|---|---|---|
| Precursor | 0.715 | 0.770 |
| LLM judge | 0.698 | 0.746 |
| Hazard search | 0.643 | 0.666 |
| YOLO in-path | 0.621 | 0.654 |
| Blend | 0.754 | 0.785 |

Hazard search on the default captions, before the precursor prompt, reached AP 0.689 on the 590 clips indexed at that point. Tables: [results/metrics.md](results/metrics.md), [results/baseline_search.md](results/baseline_search.md). Per-clip scores: [results/submission_public.csv](results/submission_public.csv).

Weather, light, scene, and time-to-accident splits need the Nexar `metadata.csv` files, which are gated. They are not in this repo.

## Layout

`app/` is the FastAPI UI. `deploy/deploy.sh` installs it on the team cluster at `/app` (public image, code in a ConfigMap). `manifests/batch_a.csv` maps Nexar ids to our uploads and contains no labels. `scripts/` rebuilds scores. `docs/architecture.md` is the data flow. `.cursor/skills/momentos/` is how we drove the pipeline.

## Reproduce

Credentials come from `/config/<team>.config` on a Builders Challenge VM. Names are listed in `config.example`.

```bash
uv venv .venv && uv pip install --python .venv/bin/python vastdb pyarrow numpy pandas boto3 scikit-learn httpx fastapi uvicorn
.venv/bin/python scripts/build_manifest.py
# labels_public.csv (id,target) goes in gitignored data/nexar/
.venv/bin/python scripts/precursor_run.py prompts/precursor_v1.txt
.venv/bin/python scripts/fill_features.py
.venv/bin/python scripts/llm_judge.py
.venv/bin/python scripts/score.py
.venv/bin/python scripts/build_app_data.py
KUBECTL=~/.local/bin/kubectl deploy/deploy.sh
```

## Credits

Moura, Daniel C., and Zvitia, Orly. "Nexar Collision Dataset." Hugging Face, 2025.
https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction

Stack: VAST DataEngine and VastDB, NVIDIA Cosmos Reason and Cosmos Embed1, Ultralytics YOLO11, Weights & Biases Inference. Code is Apache-2.0.
