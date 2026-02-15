# src/sources/wikidata.py
from __future__ import annotations

from src.utils.text import normalize_for_match

import time
from typing import Dict, List, Optional

import requests

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

DEFAULT_HEADERS = {
    "Accept": "application/sparql+json",
}


def _v(val: Optional[Dict]) -> Optional[str]:
    if not val:
        return None
    return val.get("value")


def _sparql(
    query: str,
    user_agent: str,
    timeout: int = 120,
    retries: int = 3,
    backoff_s: float = 2.0,
) -> Dict:
    headers = dict(DEFAULT_HEADERS)
    headers["User-Agent"] = user_agent

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(
                WIKIDATA_SPARQL,
                params={"query": query, "format": "json"},
                headers=headers,
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            wait = backoff_s * attempt
            print(f"[WARN] SPARQL attempt {attempt}/{retries} failed: {e}. Sleeping {wait}s")
            time.sleep(wait)

    raise last_err


def fetch_candidates_for_country(
    country_qid: str,
    category: str,
    user_agent: str = "getgridoperators/0.1 (https://github.com/open-energy-transition/getgridoperators)",
    sleep_s: float = 0.8,
    limit: int = 2000,
) -> List[Dict]:
    """
    Fast candidate fetch using instance-of types (P31/P279*) + country (P17).
    Uses strict types first; if too few results, uses fallback types and keyword filters
    using label + English description (post-query, in Python).
    """

    if category == "TSO":
        strict_types = ["Q112046"]  # transmission system operator
        fallback_types = ["Q1326624"]
        kw = ["transmission", "grid", "system operator", "operator", "electricidad", "energia"]
    elif category == "Regulator":
        # Use verified QIDs here:
        strict_types = ["Q1639780"]  # regulatory agency/body 
        fallback_types: List[str] = [] # fallback_types= ["Q327333", "Q2659904"]  # government agency/org (broad)
        kw = ["energy", "electricity", "power", "grid", "renewable", "renewables","electricidad",'energia']
    elif category == "Ministry":
        strict_types = ["Q19973795"]  #Ministry of energy
        fallback_types = ["Q1805337"] #energy policy
        kw = ["energy", "electricity", "power"]
    else:
        raise ValueError(f"Unknown category: {category}")

    def run(types: List[str]) -> List[Dict]:
        types_values = "\n".join([f"wd:{qid}" for qid in types])

        query = f"""
        SELECT ?item ?itemLabel ?country ?countryLabel ?type ?typeLabel ?website ?desc WHERE {{
          VALUES ?country {{ wd:{country_qid} }}
          VALUES ?type {{
            {types_values}
          }}

          ?item wdt:P17 ?country .
          ?item wdt:P31/wdt:P279* ?type .

          OPTIONAL {{ ?item wdt:P856 ?website. }}
          OPTIONAL {{
            ?item schema:description ?desc .
            FILTER(LANG(?desc) = "en")
          }}

          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT {limit}
        """

        data = _sparql(query, user_agent=user_agent)
        time.sleep(sleep_s)

        out: List[Dict] = []
        for b in data["results"]["bindings"]:
            item = _v(b.get("item"))
            if not item:
                continue

            qid = item.rsplit("/", 1)[-1]

            c = _v(b.get("country"))
            country_q = c.rsplit("/", 1)[-1] if c else None

            t = _v(b.get("type"))
            type_q = t.rsplit("/", 1)[-1] if t else None

            out.append(
                {
                    "source": "wikidata",
                    "category": category,
                    "operator_qid": qid,
                    "operator_label": _v(b.get("itemLabel")),
                    "operator_type_qid": type_q,
                    "operator_type_label": _v(b.get("typeLabel")),
                    "country_qid": country_q,
                    "country_label": _v(b.get("countryLabel")),
                    "website": _v(b.get("website")),
                    "description_en": _v(b.get("desc")),
                }
            )
        return out

    # ---- Decision logic ----

    # if category == "TSO":
    #     # strict only, no keyword filtering needed
    #     return run(strict_types)

    # Query strict + fallback types together, then keyword-filter
    types = list(dict.fromkeys(strict_types + fallback_types))
    rows = run(types)

    filtered: List[Dict] = []

    
    for r in rows:
        lbl = (r.get("operator_label") or "").lower()

        desc = (r.get("description_en") or "").lower()

        text = normalize_for_match(f"{lbl} {desc}")
        kw_norm = [normalize_for_match(k) for k in kw]


        if any(k in text for k in kw_norm):
            filtered.append(r)

    # print(filtered)

    return filtered
