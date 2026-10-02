# Notices

## Nexar Collision Prediction dataset

MomentOS is evaluated on, and its demo shows clips from, the Nexar Collision Prediction dataset.

> Moura, Daniel C., and Zvitia, Orly. "Nexar Collison Dataset." Hugging Face, 2025,
> https://huggingface.co/datasets/nexar-ai/nexar_collision_prediction

Copyright (c) 2025 Nexar Inc. Used under the Nexar dataset license. This repository does **not**
redistribute the dataset: no videos, labels, `solution.csv` or `metadata.csv` are committed
(`data/` and `*.mp4` are gitignored). `manifests/batch_a.csv` lists only Nexar clip ids and the
object keys of our own uploads, with no labels.

The license's ethical-use restrictions apply to any use of this project with that data, including:

- **Malicious systems:** no systems intended to cause harm, engage in unsafe driving, or simulate unsafe behavior.
- **Deepfakes and misinformation:** no manipulated media or misleading content.
- **Privacy:** no attempts to re-identify individuals, vehicles, or other entities.
- **Weaponization:** no weapon or combat systems.
- **Exploitative practices:** no exploiting accident-prone regions or individuals for predatory
  financial purposes, such as unethical insurance practices.
- **Compliance with laws.**
- **No resale:** the dataset may not be sold, sublicensed, or redistributed for profit without Nexar's consent.

MomentOS's driver score is designed around the exploitative-practices clause: it is opt-in and
driver-facing, counts only moments the driver caused, can only grant a discount or offer coaching
(never raise a premium), requires human review before any tier change, lets drivers contest any
moment, and uses no location features. The "drivers" in the demo are simulated groupings of
anonymous clips, not real people.

## Software and models

- Video pipeline and index: VAST DataEngine and VastDB (VAST Builders Challenge stack).
- NVIDIA Cosmos Reason (`cosmos3-nano-reasoner`) and Cosmos Embed1, served by the challenge organizers.
- Ultralytics YOLO11 (`yolo11s`), served by the challenge organizers.
- Weights & Biases Inference (Qwen3-30B-A3B-Instruct).

The MomentOS source code is licensed under the Apache License 2.0 (see `LICENSE`).
