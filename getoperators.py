import pandas as pd
from SPARQLWrapper import SPARQLWrapper, JSON

ENDPOINT_URL = "https://query.wikidata.org/sparql"

sparql = SPARQLWrapper(ENDPOINT_URL)
sparql.setReturnFormat(JSON)

query = """
SELECT
  ?operator ?operatorLabel
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
WHERE {
  VALUES ?operatorType {
    wd:Q112046  # transmission system operator
    wd:Q472093        # electricity distribution network operator
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
        "country_qid": r["country"]["value"].split("/")[-1],
        "country_label": r["countryLabel"]["value"],
        "website": r.get("website", {}).get("value"),
        "headquarters": r.get("hqLabel", {}).get("value"),
        "inception": r.get("inception", {}).get("value"),
        "ceo": r.get("ceoLabel", {}).get("value"),
        "employees": r.get("employees", {}).get("value"),
        "revenue": r.get("revenue", {}).get("value"),
        "industry": r.get("industryLabel", {}).get("value"),
        "logo": r.get("logo", {}).get("value"),
        "stock_exchange": r.get("stockExchangeLabel", {}).get("value"),
        "dissolved": r.get("dissolved", {}).get("value")
    })

df = pd.DataFrame(rows)

# Remove duplicate operators based on operator_qid
df = df.drop_duplicates(subset="operator_qid", keep="first")

# Save to CSV
output_file = "grid_operators_worldwide_full.csv"
df.to_csv(output_file, index=False)

print(f"✅ Done. Retrieved {len(df)} unique operators and saved to '{output_file}'.")
