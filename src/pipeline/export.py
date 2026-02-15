from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

FIELDS = [
    "source",
    "category",
    "operator_qid",
    "operator_label",
    "operator_type_qid",
    "operator_type_label",
    "country_qid",
    "country_label",
    "website",
    "description_en"
]

def write_csv(path: str, rows: List[Dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
