from __future__ import annotations

from typing import Dict, List, Set

def filter_to_ggc(rows: List[Dict], ggc_country_qids: Set[str]) -> List[Dict]:
    out = []
    for r in rows:
        cq = (r.get("country_qid") or "").strip()
        if cq and cq in ggc_country_qids:
            out.append(r)
    return out

def filter_relevant(rows: List[Dict]) -> List[Dict]:
    """
    Light filter to drop obvious junk.
    We'll improve later using instance-of rules.
    """
    out = []
    for r in rows:
        lbl = (r.get("operator_label") or "").lower()
        desc = (r.get("description_en") or "").lower()

        # drop obvious non-org items if any slip through
        if not lbl:
            continue

        text = f"{lbl} {desc}"
        if r.get("category") == "TSO":
            keep = any(k in text for k in ["transmission", "system operator", "grid operator", "tsO".lower()])
        elif r.get("category") == "Regulator":
            keep = any(k in text for k in ["regulator", "regulatory", "commission", "authority"])
        elif r.get("category") == "Ministry":
            keep = any(k in text for k in ["ministry", "department"])
        else:
            keep = True

        if keep:
            out.append(r)

    return out
