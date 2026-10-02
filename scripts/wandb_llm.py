"""W&B Inference (OpenAI-compatible) chat helper. Uses WANDB_API_KEY / WANDB_TEAM / WANDB_PROJECT."""
import json
import os
import re
import time

import httpx

BASE = "https://api.inference.wandb.ai/v1"
DEFAULT_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"


def chat(messages, model=DEFAULT_MODEL, max_tokens=300, temperature=0.0):
    headers = {"Authorization": f"Bearer {os.environ['WANDB_API_KEY']}",
               "OpenAI-Project": f"{os.environ['WANDB_TEAM']}/{os.environ['WANDB_PROJECT']}"}
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    for attempt in range(4):
        r = httpx.post(f"{BASE}/chat/completions", headers=headers, json=body, timeout=90)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(3 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def chat_json(messages, **kw):
    text = chat(messages, **kw)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group()) if m else {}
