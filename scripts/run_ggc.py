# scripts/run_ggc.py
from __future__ import annotations

import csv
import sys
from pathlib import Path
import requests

# Ensure repo root is on sys.path so `import src...` works regardless of cwd
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.utils.paths import project_root
from src.sources.wikidata import fetch_candidates_for_country
from src.pipeline.filter import filter_relevant #not used at the moment, filtering is done in wikidata.py
from src.pipeline.export import write_csv
from src.utils.text import dedupe_rows

WIKIDATA_SEARCH = "https://www.wikidata.org/w/api.php"


def country_label_to_qid(label: str, user_agent: str) -> str | None:
    params = {
        "action": "wbsearchentities",
        "search": label,
        "language": "en",
        "format": "json",
        "limit": 5,
        "type": "item",
    }
    r = requests.get(WIKIDATA_SEARCH, params=params, headers={"User-Agent": user_agent}, timeout=30)
    r.raise_for_status()
    data = r.json()

    # Prefer exact label match
    for hit in data.get("search", []):
        if (hit.get("label") or "").lower() == label.lower():
            return hit.get("id")

    # Fallback: first hit
    if data.get("search"):
        return data["search"][0].get("id")

    return None


def load_ggc_countries(csv_path: Path):
    out = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            c = (row.get("country_label") or "").strip()
            t = (row.get("tier") or "").strip()
            if c:
                out.append((t, c))
    return out


def main():
    ROOT = project_root(Path(__file__))
    DATA_DIR = ROOT / "data"
    OUT_DIR = ROOT / "outputs"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    user_agent = "getgridoperators/0.1 (https://github.com/open-energy-transition/getgridoperators)"

    ggc_csv = DATA_DIR / "ggc_country_tiers.csv"
    if not ggc_csv.exists():
        raise FileNotFoundError(f"Missing file: {ggc_csv}")

    countries = load_ggc_countries(ggc_csv)

    # Resolve country labels to QIDs
    ggc_country_qids: dict[str, str] = {}
    for tier, label in countries:
        qid = country_label_to_qid(label, user_agent=user_agent)
        if not qid:
            print(f"[WARN] Could not resolve country to QID: {label} (tier {tier})")
            continue
        ggc_country_qids[label] = qid

    all_rows = []

    for country_label, country_qid in ggc_country_qids.items():
        for category in ["TSO", "Regulator", "Ministry"]:
            print(f"[INFO] {country_label} ({country_qid}) -> {category}")

            try:
                rows = fetch_candidates_for_country(
                    country_qid,
                    category,
                    user_agent=user_agent,
                    sleep_s=0.5,
                    limit=2000,
                )
                all_rows.extend(rows)
            except Exception as e:
                print(f"[ERROR] Failed {country_label} ({country_qid}) -> {category}: {e}")
                continue

    # Light relevance + dedupe
    all_rows = dedupe_rows(all_rows, key_fields=["operator_qid", "category", "country_qid"])

    out_path = OUT_DIR / "ggc_wikidata_candidates.csv"
    write_csv(str(out_path), all_rows)
    print(f"[DONE] Wrote {out_path} rows={len(all_rows)}")


if __name__ == "__main__":
    main()
