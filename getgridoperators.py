import csv
from pathlib import Path
import pandas as pd
import requests
from SPARQLWrapper import SPARQLWrapper, JSON
from difflib import SequenceMatcher
import time

def load_names(csv_path="data/names_seed.csv"):
    names = []
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            if name:
                names.append(name)
    return names

names = load_names()

# ----------------------------
# Part 0: Setup
# ----------------------------
ENDPOINT_URL = "https://query.wikidata.org/sparql"
sparql = SPARQLWrapper(ENDPOINT_URL)
sparql.setReturnFormat(JSON)

# ----------------------------
# Part 1: Collect operators by types (with optional Wikipedia links)
# ----------------------------

query = """
SELECT
  ?operator ?operatorLabel
  ?operatorType ?operatorTypeLabel
  ?country ?countryLabel
  ?website
  ?hqLabel
  ?inception
  ?ceoLabel
  ?employees
  ?revenue
  ?industryLabel
  ?logo
  ?stockExchangeLabel
  ?dissolved
  ?parentOrgLabel
  ?ownedByLabel
  ?legalFormLabel
  ?linkedin
  ?twitter
  ?crunchbase
  ?bloombergTicker
  ?netProfit
  ?installedCapacity
  ?wikiArticle
WHERE {
  VALUES ?operatorType {
    wd:Q112046  # transmission system operator
    wd:Q472093  # electricity distribution network operator
    wd:Q1326624 # electricity supply company
    wd:Q200928  # electric power transmission
    wd:Q7236594 # power pool
    wd:Q137883267  # power generation company
    wd:Q1326594 # electric power generation, transmission and distribution 
    wd:Q1341477 # energy supply
    wd:Q383973 # electricity generation
  }

  ?operator wdt:P31 ?operatorType ;
            wdt:P17 ?country .

  OPTIONAL { ?operator wdt:P856 ?website . }
  OPTIONAL { ?operator wdt:P159 ?hq . }
  OPTIONAL { ?operator wdt:P571 ?inception . }
  OPTIONAL { ?operator wdt:P169 ?ceo . }
  OPTIONAL { ?operator wdt:P1128 ?employees . }
  OPTIONAL { ?operator wdt:P2139 ?revenue . }
  OPTIONAL { ?operator wdt:P452 ?industry . }
  OPTIONAL { ?operator wdt:P154 ?logo . }
  OPTIONAL { ?operator wdt:P414 ?stockExchange . }
  OPTIONAL { ?operator wdt:P576 ?dissolved . }

  # Additional requested properties
  OPTIONAL { ?operator wdt:P749 ?parentOrg . }
  OPTIONAL { ?operator wdt:P127 ?ownedBy . }
  OPTIONAL { ?operator wdt:P1454 ?legalForm . }
  OPTIONAL { ?operator wdt:P4264 ?linkedin . }
  OPTIONAL { ?operator wdt:P2002 ?twitter . }
  OPTIONAL { ?operator wdt:P2088 ?crunchbase . }
  OPTIONAL { ?operator wdt:P414 ?bloombergTicker . }
  OPTIONAL { ?operator wdt:P2295 ?netProfit . }
  OPTIONAL { ?operator wdt:P2109 ?installedCapacity . }

  # Optional Wikipedia link
  OPTIONAL {
    ?wikiArticle schema:about ?operator ;
                 schema:isPartOf <https://en.wikipedia.org/> .
  }

  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en".
  }
}
ORDER BY ?countryLabel ?operatorLabel
"""

sparql.setQuery(query)
results = sparql.query().convert()["results"]["bindings"]

rows = []
for r in results:
    rows.append({
        "operator_qid": r["operator"]["value"].split("/")[-1],
        "operator_label": r["operatorLabel"]["value"],
        "operator_type_qid": r.get("operatorType", {}).get("value", "").split("/")[-1] if r.get("operatorType") else None,
        "operator_type_label": r.get("operatorTypeLabel", {}).get("value"),
        "country_qid": r.get("country", {}).get("value", "").split("/")[-1] if r.get("country") else None,
        "country_label": r.get("countryLabel", {}).get("value"),
        "website": r.get("website", {}).get("value"),
        "headquarters": r.get("hqLabel", {}).get("value"),
        "inception": r.get("inception", {}).get("value"),
        "ceo": r.get("ceoLabel", {}).get("value"),
        "employees": r.get("employees", {}).get("value"),
        "revenue": r.get("revenue", {}).get("value"),
        "industry": r.get("industryLabel", {}).get("value"),
        "logo": r.get("logo", {}).get("value"),
        "stock_exchange": r.get("stockExchangeLabel", {}).get("value"),
        "dissolved": r.get("dissolved", {}).get("value"),
        "parent_organization": r.get("parentOrgLabel", {}).get("value"),
        "owned_by": r.get("ownedByLabel", {}).get("value"),
        "legal_form": r.get("legalFormLabel", {}).get("value"),
        "linkedin": r.get("linkedin", {}).get("value"),
        "twitter": r.get("twitter", {}).get("value"),
        "crunchbase": r.get("crunchbase", {}).get("value"),
        "bloomberg_ticker": r.get("bloombergTicker", {}).get("value"),
        "net_profit": r.get("netProfit", {}).get("value"),
        "installed_capacity": r.get("installedCapacity", {}).get("value"),
        "wikipedia": r.get("wikiArticle", {}).get("value")  # optional
    })

df_types = pd.DataFrame(rows)
df_types = df_types.drop_duplicates(subset="operator_qid", keep="first")
print(f"✅ Retrieved {len(df_types)} unique operators by type.")

# ----------------------------
# Part 2: Collect operators by names
# ----------------------------

def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

ALLOWED_INSTANCE_QIDS = {
    "Q4830453",  # business
    "Q783794", # company
    "Q6881511", # enterprise
    "Q891723", # public company
    "Q1951366", # public utility
    "Q197952", # corporate group
    "Q270791", # state-owned enterprise
    "Q327333", # government agency
    "Q194166", # consortium
    "Q192350", # ministryI want
    "Q15911314", # association
    "Q163740", #nonprofit organization
    "Q4539", # cooperative
    "Q2316331", #electric power industry
    "Q245065", # intergovernmental organization"
    "Q43229", #organization
    "Q2396633", # state property
    "Q1639780", # regulatory agency
    "Q2659904", # government organization
    "Q55657615", # commission
    "Q112046",  # transmission system operator
    "Q472093",  # electricity distribution network operator
    "Q1326624", # electricity supply company
    "Q200928",  # electric power transmission
    "Q7236594", # power pool
    "Q137883267",  # power generation company
    "Q1096907",
    "Q107594896" # energy and water industrie
}

def search_wikidata(name, limit=10, fuzzy_threshold=0.6, max_fallbacks=3):
    """Search Wikidata for a name with detailed debug output."""

    def _search(query):
        print(f"\n🔍 Searching for: '{query}'")
        url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbsearchentities",
            "search": query,
            "language": "en",
            "format": "json",
            "type": "item",
            "limit": limit
        }
        headers = {"User-Agent": "MyWikidataScript/1.0 (your_email@example.com)"}
        response = requests.get(url, params=params, headers=headers)
        try:
            data = response.json()
        except Exception as e:
            print(f"❌ Error decoding JSON for '{query}': {e}")
            return []

        results = []
        for item in data.get("search", []):
            qid = item["id"]
            label = item["label"]
            print(f"  Candidate found: {label} ({qid})")

            # Fetch instance of (P31) for this entity
            entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
            entity_data = requests.get(entity_url, headers=headers).json()
            claims = entity_data.get("entities", {}).get(qid, {}).get("claims", {})
            instance_of_qids = {c["mainsnak"]["datavalue"]["value"]["id"] 
                                for c in claims.get("P31", []) 
                                if "datavalue" in c["mainsnak"]}

            if not instance_of_qids.intersection(ALLOWED_INSTANCE_QIDS):
                print(f"    ❌ Rejected: instance type {instance_of_qids} not allowed")
                continue

            score = similarity(query, label)
            print(f"    Similarity with query: {score:.2f}")
            if score >= fuzzy_threshold:
                print(f"    ✅ Accepted match")
                results.append((qid, label, score))
            else:
                print(f"    ❌ Rejected: similarity {score:.2f} < threshold {fuzzy_threshold}")

        results.sort(key=lambda x: x[2], reverse=True)
        return results

    current_name = name
    attempts = 0
    while current_name and attempts <= max_fallbacks:
        if attempts > 0:
            print(f"\n⚠️ Fallback attempt {attempts}: using truncated name '{current_name}'")
        results = _search(current_name)
        if results:
            print(f"✅ Matches found for '{current_name}'\n")
            return results
        # Truncate the last word for next fallback
        if " " in current_name:
            removed_word = current_name.split()[-1]
            current_name = " ".join(current_name.split()[:-1])
            print(f"  Removing last word '{removed_word}', trying '{current_name}' next...")
            attempts += 1
        else:
            break

    print(f"❌ No matches found for '{name}' after {attempts} fallback attempts\n")
    return []


# Example: names = ["Company A", "Company B"]
wikidata_name_results = []
for name in names:
    results = search_wikidata(name)
    if results:
        for entity_id, label, score in results:
            wikidata_name_results.append({
                "operator_name": name,
                "operator_qid": entity_id,
                "operator_label": label,
                "similarity_score": score
            })
    else:
        wikidata_name_results.append({
            "operator_name": name,
            "operator_qid": None,
            "operator_label": None,
            "similarity_score": None
        })

df_names = pd.DataFrame(wikidata_name_results)

# ----------------------------
# Part 3: Fetch missing metadata from Wikidata for new QIDs (with Wikipedia + extra fields)
# ----------------------------

def fetch_operator_metadata(qid):
    """SPARQL fetch operator info by QID, including requested extra fields"""
    if not qid:
        return None
    query = f"""
    SELECT
      ?operator ?operatorLabel
      ?operatorType ?operatorTypeLabel
      ?country ?countryLabel
      ?website
      ?hqLabel
      ?inception
      ?ceoLabel
      ?employees
      ?revenue
      ?industryLabel
      ?logo
      ?stockExchangeLabel
      ?dissolved
      ?parentOrgLabel
      ?ownedByLabel
      ?legalFormLabel
      ?linkedin
      ?twitter
      ?crunchbase
      ?bloombergTicker
      ?netProfit
      ?installedCapacity
      ?wikiArticle
    WHERE {{
      BIND(wd:{qid} AS ?operator)
      OPTIONAL {{ ?operator wdt:P31 ?operatorType. }}
      OPTIONAL {{ ?operator wdt:P17 ?country. }}
      OPTIONAL {{ ?operator wdt:P856 ?website. }}
      OPTIONAL {{ ?operator wdt:P159 ?hq. }}
      OPTIONAL {{ ?operator wdt:P571 ?inception. }}
      OPTIONAL {{ ?operator wdt:P169 ?ceo. }}
      OPTIONAL {{ ?operator wdt:P1128 ?employees. }}
      OPTIONAL {{ ?operator wdt:P2139 ?revenue. }}
      OPTIONAL {{ ?operator wdt:P452 ?industry. }}
      OPTIONAL {{ ?operator wdt:P154 ?logo. }}
      OPTIONAL {{ ?operator wdt:P414 ?stockExchange. }}
      OPTIONAL {{ ?operator wdt:P576 ?dissolved. }}
      OPTIONAL {{ ?operator wdt:P749 ?parentOrg. }}
      OPTIONAL {{ ?operator wdt:P127 ?ownedBy. }}
      OPTIONAL {{ ?operator wdt:P1454 ?legalForm. }}
      OPTIONAL {{ ?operator wdt:P4264 ?linkedin. }}
      OPTIONAL {{ ?operator wdt:P2002 ?twitter. }}
      OPTIONAL {{ ?operator wdt:P2088 ?crunchbase. }}
      OPTIONAL {{ ?operator wdt:P414 ?bloombergTicker. }}
      OPTIONAL {{ ?operator wdt:P2295 ?netProfit. }}
      OPTIONAL {{ ?operator wdt:P2109 ?installedCapacity. }}
      OPTIONAL {{
        ?wikiArticle schema:about ?operator ;
                     schema:isPartOf <https://en.wikipedia.org/> .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    sparql.setQuery(query)
    try:
        result = sparql.query().convert()["results"]["bindings"]
        if not result:
            return None
        r = result[0]
        return {
            "operator_qid": qid,
            "operator_label": r.get("operatorLabel", {}).get("value"),
            "operator_type_qid": r.get("operatorType", {}).get("value", "").split("/")[-1] if r.get("operatorType") else None,
            "operator_type_label": r.get("operatorTypeLabel", {}).get("value"),
            "country_qid": r.get("country", {}).get("value", "").split("/")[-1] if r.get("country") else None,
            "country_label": r.get("countryLabel", {}).get("value"),
            "website": r.get("website", {}).get("value"),
            "headquarters": r.get("hqLabel", {}).get("value"),
            "inception": r.get("inception", {}).get("value"),
            "ceo": r.get("ceoLabel", {}).get("value"),
            "employees": r.get("employees", {}).get("value"),
            "revenue": r.get("revenue", {}).get("value"),
            "industry": r.get("industryLabel", {}).get("value"),
            "logo": r.get("logo", {}).get("value"),
            "stock_exchange": r.get("stockExchangeLabel", {}).get("value"),
            "dissolved": r.get("dissolved", {}).get("value"),
            "parent_organization": r.get("parentOrgLabel", {}).get("value"),
            "owned_by": r.get("ownedByLabel", {}).get("value"),
            "legal_form": r.get("legalFormLabel", {}).get("value"),
            "linkedin": r.get("linkedin", {}).get("value"),
            "twitter": r.get("twitter", {}).get("value"),
            "crunchbase": r.get("crunchbase", {}).get("value"),
            "bloomberg_ticker": r.get("bloombergTicker", {}).get("value"),
            "net_profit": r.get("netProfit", {}).get("value"),
            "installed_capacity": r.get("installedCapacity", {}).get("value"),
            "wikipedia": r.get("wikiArticle", {}).get("value")
        }
    except Exception as e:
        print(f"Error fetching metadata for {qid}: {e}")
        return None

# Fetch metadata for new QIDs not already in df_types
new_qids = set(df_names["operator_qid"]) - set(df_types["operator_qid"])
metadata_rows = []
for qid in new_qids:
    data = fetch_operator_metadata(qid)
    if data:
        metadata_rows.append(data)
    time.sleep(0.3)  # polite delay

df_new_metadata = pd.DataFrame(metadata_rows)

# ----------------------------
# Part 4: Combine datasets
# ----------------------------

df_combined = pd.concat([df_types, df_new_metadata], ignore_index=True)

# Optional: merge similarity info from name search
df_combined = df_combined.merge(
    df_names[["operator_qid", "similarity_score", "operator_name"]],
    on="operator_qid",
    how="left"
)

df_combined = df_combined.drop_duplicates(subset="operator_qid", keep="first")

# ----------------------------
# Part 5: Save final combined CSV
# ----------------------------

df_combined.to_csv("grid_operators_combined.csv", index=False)
print(f"✅ Combined dataset saved with {len(df_combined)} operators to 'grid_operators_combined.csv'.")
