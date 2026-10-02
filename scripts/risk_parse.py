"""Parse the structured precursor caption (prompts/precursor_v1.txt) into fields."""
import re

CUE_VOCAB = {"hard_braking_ahead", "brake_lights_ahead", "cut_in", "vehicle_crossing_path", "oncoming_in_lane",
             "pedestrian_in_path", "cyclist_in_path", "ego_speeding", "ego_tailgating", "ego_lane_drift",
             "ego_red_light", "occlusion", "low_visibility"}
EGO_CUES = {"ego_speeding", "ego_tailgating", "ego_lane_drift", "ego_red_light"}


def _field(text, name):
    m = re.search(rf"^\s*\**{name}\**\s*[=:]\s*(.+?)\s*$", text or "", re.I | re.M)
    return m.group(1).strip() if m else None


def parse(text):
    """Return a dict with risk (float|None), cause, ttc, lead, ego, cues (set), summary, structured (bool)."""
    risk = _field(text, "RISK")
    risk_m = re.search(r"\d+(\.\d+)?", risk or "")
    ttc = _field(text, "TTC")
    ttc_m = re.search(r"\d+(\.\d+)?", ttc or "")
    cues_raw = (_field(text, "CUES") or "").lower()
    cues = {c for c in re.split(r"[,\s;]+", cues_raw) if c in CUE_VOCAB}
    cause = (_field(text, "CAUSE") or "").lower()
    cause = next((c for c in ("ego", "other", "none") if cause.startswith(c)), None)
    out = {
        "risk": min(10.0, float(risk_m.group())) if risk_m else None,
        "cause": cause,
        "ttc": float(ttc_m.group()) if ttc_m else None,
        "lead": (_field(text, "LEAD") or "").lower() or None,
        "ego": (_field(text, "EGO") or "").lower() or None,
        "cues": cues,
        "summary": _field(text, "SUMMARY"),
    }
    out["structured"] = out["risk"] is not None
    return out
