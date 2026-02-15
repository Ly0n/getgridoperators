#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import getpass
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Make src importable
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.utils.text import normalize_for_match
from src.utils.paths import project_root


# NOTE:
# - We do NOT mix agencies into Regulator.
# - Agencies are separate categories (RenewablesAgency, NuclearAgency).
CATEGORIES: List[Tuple[str, str]] = [
    ("TSO", "transmission system operator (TSO) / national grid or system operator"),
    ("Regulator", "electricity/energy regulator with formal regulatory authority (tariffs, licensing, compliance, grid access)"),
    ("Ministry", "cabinet-level ministry responsible for energy/electricity policy"),
    ("RenewablesAgency", "national renewable energy agency (promotion/implementation body, incentives, programs, certification)"),
    ("NuclearAgency", "national nuclear/atomic agency or nuclear safety regulator (nuclear governance, safety, licensing, atomic energy commission)"),
]


@dataclass
class SeedRow:
    country_label: str
    category: str
    name: str
    also_known_as: str
    official_website: str
    confidence: str
    evidence: str
    comment: str
    source: str = "chatgpt"


def get_openai_client():
    """
    Gets OpenAI client.
    1. Tries OPENAI_API_KEY env variable.
    2. If not present, securely prompts user.
    """
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        api_key = getpass.getpass("Enter your OpenAI API key: ").strip()

    if not api_key:
        raise RuntimeError("No OpenAI API key provided.")

    return OpenAI(api_key=api_key)


def load_ggc_countries(path: Path) -> List[str]:
    countries: List[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if "country_label" not in (r.fieldnames or []):
            raise ValueError(f"Expected column 'country_label' in {path}")
        for row in r:
            c = (row.get("country_label") or "").strip()
            if c:
                countries.append(c)

    # stable unique
    seen = set()
    out = []
    for c in countries:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def load_manual_seed_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()

    keys = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if "name" not in (r.fieldnames or []):
            raise ValueError(f"Expected column 'name' in {path}")
        for row in r:
            nm = (row.get("name") or "").strip()
            if nm:
                keys.add(normalize_for_match(nm))
    return keys


def _category_tests_block(category_key: str) -> str:
    if category_key == "TSO":
        return (
            "- TSO test: entity responsible for transmission system operation/balancing/dispatch at national or regional level. "
            "May be called TSO, ISO, RTO, system operator, national grid operator. "
            "If vertically integrated, state that.\n"
        )
    if category_key == "Regulator":
        return (
            "- Regulator test: formal regulatory authority over electricity/energy (tariffs, licensing, enforcement, market/grid access). "
            "Do NOT include renewables agencies or nuclear agencies unless they regulate electricity markets.\n"
        )
    if category_key == "Ministry":
        return (
            "- Ministry test: cabinet-level ministry setting national energy/electricity policy. "
            "Do NOT list regulators or implementing agencies.\n"
        )
    if category_key == "RenewablesAgency":
        return (
            "- RenewablesAgency test: national-level public body implementing/promoting renewable energy programs "
            "(incentives, auctions/programs, certification, deployment support). "
            "Do NOT list NGOs or private associations. If none exists, return empty.\n"
        )
    if category_key == "NuclearAgency":
        return (
            "- NuclearAgency test: national nuclear safety regulator and/or atomic energy commission/authority with official mandate "
            "for nuclear governance (safety, licensing, oversight, atomic energy development). "
            "If none exists, return empty.\n"
        )
    return ""


def _build_primary_prompt(*, country: str, category_key: str, category_desc: str, max_items: int) -> str:
    return (
        "You are an expert in electricity-sector institutional structures.\n\n"
        f"Country: {country}\n"
        f"Category required: {category_key} ({category_desc})\n\n"
        "Decision process (follow strictly):\n"
        "1) Determine the institutional structure relevant to this category:\n"
        "   - Centralized single national body\n"
        "   - Multiple legally designated bodies by region\n"
        "   - ISO/RTO structure (regional system operators)\n"
        "   - Split authority across multiple formal agencies\n\n"
        "2) Listing rules:\n"
        "- If centralized: return ONLY the single primary national-level institution.\n"
        "- If multiple legally designated bodies exist: return ALL primary bodies (national or formally designated regions), but do not exceed max.\n"
        "- If ISO/RTO structure exists (e.g., US): return the primary regional system operators (avoid minor/subregional ones), but do not exceed max.\n"
        "- Never list provincial/municipal entities.\n"
        "- Never list NGOs, industry associations, donor programs, or advisory councils.\n\n"
        f"Category tests:\n{_category_tests_block(category_key)}\n"
        f"Hard cap: Return no more than {max_items} items.\n"
        "If none exists for this category, return items as an empty array.\n\n"
        "Output requirements:\n"
        "- Return JSON only.\n"
        "- For each item, you MUST return ALL fields (use empty string \"\" when unknown):\n"
        "  name, also_known_as, official_website, confidence, evidence, comment\n"
        "- confidence must be HIGH, MED, or LOW.\n"
    )


def _build_verify_prompt(*, country: str, category_key: str, category_desc: str, candidate_name: str) -> str:
    return (
        "You are validating a candidate institution name for a country and category.\n\n"
        f"Country: {country}\n"
        f"Category: {category_key} ({category_desc})\n"
        f"Candidate: {candidate_name}\n\n"
        "Task:\n"
        "If the candidate is truly a correct primary match for the category, keep it (may correct official naming).\n"
        "If not, replace it with the correct primary institution (or return empty if none exists).\n\n"
        "Rules:\n"
        "- Do not overlist. Prefer only primary bodies.\n"
        "- Never mix categories.\n"
        f"{_category_tests_block(category_key)}\n"
        "- Return JSON only.\n"
        "- You MUST return ALL fields (use empty string \"\" when unknown):\n"
        "  name, also_known_as, official_website, confidence, evidence, comment\n"
        "- confidence MUST be HIGH, MED, or LOW.\n"
    )


def _json_schema(max_items: int) -> Dict:
    """
    OpenAI's json_schema response_format requires that within an object schema using
    additionalProperties:false, the 'required' array includes every key in 'properties'.
    So we make all fields required and allow empty strings.
    """
    item_properties = {
        "name": {"type": "string"},
        "also_known_as": {"type": "string"},
        "official_website": {"type": "string"},
        "confidence": {"type": "string", "enum": ["HIGH", "MED", "LOW"]},
        "evidence": {"type": "string"},
        "comment": {"type": "string"},
    }

    return {
        "name": "ggc_seeds",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "items": {
                    "type": "array",
                    "maxItems": max_items,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": item_properties,
                        "required": list(item_properties.keys()),
                    },
                }
            },
            "required": ["items"],
        },
        "strict": True,
    }


def _format_json_schema_for_responses(schema_obj: Dict) -> Dict:
    # Required by Responses API: text.format = {type, name, schema}
    return {
        "type": "json_schema",
        "name": schema_obj["name"],
        "schema": schema_obj["schema"],
    }


def _safe_parse_items(resp_output_text: str) -> List[Dict[str, str]]:
    try:
        obj = json.loads(resp_output_text)
    except json.JSONDecodeError:
        return []

    items = obj.get("items", [])
    if not isinstance(items, list):
        return []

    out: List[Dict[str, str]] = []
    for it in items:
        if not isinstance(it, dict):
            continue

        name = (it.get("name") or "").strip()
        also_known_as = (it.get("also_known_as") or "").strip()
        official_website = (it.get("official_website") or "").strip()
        confidence = (it.get("confidence") or "").strip()
        evidence = (it.get("evidence") or "").strip()
        comment = (it.get("comment") or "").strip()

        if not name:
            continue
        if confidence not in {"HIGH", "MED", "LOW"}:
            confidence = "LOW"

        out.append(
            {
                "name": name,
                "also_known_as": also_known_as,
                "official_website": official_website,
                "confidence": confidence,
                "evidence": evidence,
                "comment": comment,
            }
        )
    return out


def call_chatgpt(
    client,
    *,
    country: str,
    category_key: str,
    category_desc: str,
    model: str,
    max_items: int,
    temperature: float,
) -> List[Dict[str, str]]:
    prompt = _build_primary_prompt(
        country=country,
        category_key=category_key,
        category_desc=category_desc,
        max_items=max_items,
    )
    schema_obj = _json_schema(max_items)

    resp = client.responses.create(
        model=model,
        input=prompt,
        temperature=temperature,
        text={"format": _format_json_schema_for_responses(schema_obj)},
    )

    return _safe_parse_items(resp.output_text)


def verify_item(
    client,
    *,
    country: str,
    category_key: str,
    category_desc: str,
    candidate_name: str,
    model: str,
    temperature: float,
) -> Optional[Dict[str, str]]:
    prompt = _build_verify_prompt(
        country=country,
        category_key=category_key,
        category_desc=category_desc,
        candidate_name=candidate_name,
    )
    schema_obj = _json_schema(1)

    resp = client.responses.create(
        model=model,
        input=prompt,
        temperature=temperature,
        text={"format": _format_json_schema_for_responses(schema_obj)},
    )

    items = _safe_parse_items(resp.output_text)
    return items[0] if items else None


def write_csv(path: Path, rows: List[SeedRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "country_label",
                "category",
                "name",
                "also_known_as",
                "official_website",
                "confidence",
                "evidence",
                "comment",
                "source",
            ],
        )
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "country_label": r.country_label,
                    "category": r.category,
                    "name": r.name,
                    "also_known_as": r.also_known_as,
                    "official_website": r.official_website,
                    "confidence": r.confidence,
                    "evidence": r.evidence,
                    "comment": r.comment,
                    "source": r.source,
                }
            )


def main():
    parser = argparse.ArgumentParser(description="Generate ChatGPT seed list.")
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument(
        "--max-items",
        type=int,
        default=5,
        help="Hard cap per (country, category). Prompt logic prevents overlisting small countries.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Lower is more deterministic. Best quality usually 0.0-0.2.",
    )
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run a second-pass verifier per returned item (best accuracy, more calls).",
    )
    parser.add_argument("--dedupe-against-manual", action="store_true")
    args = parser.parse_args()

    ROOT = project_root(Path(__file__))
    data_dir = ROOT / "data"
    outputs_dir = ROOT / "outputs"

    countries = load_ggc_countries(data_dir / "ggc_country_tiers.csv")

    manual_keys = set()
    if args.dedupe_against_manual:
        manual_keys = load_manual_seed_keys(data_dir / "names_seed.csv")
        print(f"[INFO] Loaded {len(manual_keys)} manual seeds for dedupe")

    client = get_openai_client()

    rows: List[SeedRow] = []
    seen_keys = set()

    for country in countries:
        for cat_key, cat_desc in CATEGORIES:
            print(f"[INFO] Seeding {country} -> {cat_key}")

            items = call_chatgpt(
                client,
                country=country,
                category_key=cat_key,
                category_desc=cat_desc,
                model=args.model,
                max_items=args.max_items,
                temperature=args.temperature,
            )

            # Optional second-pass verification (best accuracy; costs more API calls)
            if args.verify and items:
                verified: List[Dict[str, str]] = []
                for it in items:
                    v = verify_item(
                        client,
                        country=country,
                        category_key=cat_key,
                        category_desc=cat_desc,
                        candidate_name=it["name"],
                        model=args.model,
                        temperature=max(0.0, min(0.2, args.temperature)),
                    )
                    verified.append(v if v else it)
                    time.sleep(args.sleep)
                items = verified

            for it in items:
                k = normalize_for_match(it["name"])
                if not k:
                    continue
                if k in seen_keys:
                    continue
                if args.dedupe_against_manual and k in manual_keys:
                    continue

                seen_keys.add(k)
                rows.append(
                    SeedRow(
                        country_label=country,
                        category=cat_key,
                        name=it.get("name", ""),
                        also_known_as=it.get("also_known_as", ""),
                        official_website=it.get("official_website", ""),
                        confidence=it.get("confidence", ""),
                        evidence=it.get("evidence", ""),
                        comment=it.get("comment", ""),
                        source="chatgpt",
                    )
                )

            time.sleep(args.sleep)

    out_path = outputs_dir / "ggc_chatgpt_seeds.csv"
    write_csv(out_path, rows)
    print(f"[DONE] Wrote {out_path} rows={len(rows)}")


if __name__ == "__main__":
    main()
