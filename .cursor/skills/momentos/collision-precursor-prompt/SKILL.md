---
name: collision-precursor-prompt
description: >-
  Design, test and parse the Cosmos Reason ingestion prompt that turns dashcam segments into a fixed
  RISK/CAUSE/TTC/LEAD/EGO/CUES/SUMMARY answer. Use when editing prompts/precursor_*.txt, probing a
  prompt on a few clips before re-ingest, or parsing structured captions.
---

# Collision-precursor prompt

## Why

Nexar positives stop before impact, and default captions describe scenery ("no signs of erratic
driving"). The prompt must ask for *precursors* in the final seconds and for *who* creates the danger.

## Current prompt

`prompts/precursor_v1.txt` (753 chars; limit 800). Output contract, one field per line:

```
RISK=<0-10>  CAUSE=<ego|other|none>  TTC=<s|none>  LEAD=<closing_fast|closing|steady|none>
EGO=<stopped|slow|moderate|fast>  CUES=<comma list from fixed vocabulary>  SUMMARY=<one sentence>
```

Parse with `scripts/risk_parse.py::parse(text)`; `EGO_CUES` are the cues attributable to the driver.

## Iterate without touching the index

```bash
.venv/bin/python scripts/prompt_probe.py prompts/precursor_v2.txt --pos 5 --neg 5
.venv/bin/python scripts/prompt_probe.py prompts/precursor_v2.txt --ids 00230,01264
```

Calls Cosmos Reason directly on the segment files from S3 (4 workers, retries on 502) and prints old
vs new captions with parsed fields. Writes only to `/tmp`.

## Checks before adopting a new version

1. 100% of answers parse (`structured`), on ≥10 clips.
2. Last-segment RISK separates positives and negatives on the probe set.
3. CAUSE is plausible on clips with cut-ins (other) vs ego turns or tailgating (ego).
4. Never include labels, ids, or dataset names in the prompt.
5. Bump the file name (`precursor_v2.txt`); `prompt_version` is recorded with every caption.
