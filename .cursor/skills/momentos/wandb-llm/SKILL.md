---
name: wandb-llm
description: >-
  Call Weights & Biases serverless inference (OpenAI-compatible) for MomentOS app logic: the per-clip
  LLM risk judge and driver coaching notes. Use when adding LLM reasoning on top of VSS results or
  when W&B calls fail.
---

# W&B Inference for MomentOS

- Base URL `https://api.inference.wandb.ai/v1`, headers `Authorization: Bearer $WANDB_API_KEY` and
  `OpenAI-Project: $WANDB_TEAM/$WANDB_PROJECT`. Env names only; never print values.
- Default model `Qwen/Qwen3-30B-A3B-Instruct-2507` (fast, instruction-tuned, no thinking tokens).
  List models with `GET /v1/models`.
- Python's default `urllib` user agent gets **403**; use `httpx` (as `scripts/wandb_llm.py` does).

## Helpers

```python
from wandb_llm import chat, chat_json   # scripts/wandb_llm.py
chat_json([{"role": "system", "content": "..."}, {"role": "user", "content": "..."}])
```

## Uses in MomentOS

| Use | Where | Input |
|---|---|---|
| Clip risk judge (score component, 25%) | `scripts/llm_judge.py` → `results/llm_judge.jsonl` | the clip's structured segment captions (text only) |
| Driver coaching note | `app/main.py` `POST /api/riders/{id}/coach` | the driver's flagged moments; must not mention premium increases |

Never send labels, tags, or anything identifying people or vehicles.
