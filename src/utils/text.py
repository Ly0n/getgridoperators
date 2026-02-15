from __future__ import annotations

import re
import unicodedata

def normalize_name(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s&.-]", "", s)
    return s.strip()

def dedupe_rows(rows, key_fields):
    seen = set()
    out = []
    for r in rows:
        key = tuple((r.get(f) or "").strip() for f in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
