import requests
import time
import pandas as pd
from tqdm import tqdm
from collections import Counter
from datetime import datetime

# ==========================
# CONFIGURATION
# ==========================

API_KEY = ""  # Optional: Insert your Semantic Scholar API key here
QUERY = '"PLEXOS" AND "energy"'
FIELDS = "title,year,abstract,citationCount,authors,authors.affiliations,externalIds"
LIMIT_PER_REQUEST = 100  # Max allowed per request
MAX_PAPERS = 10000        # Total papers to retrieve
REQUEST_DELAY = 1.0      # Seconds between requests (increase if rate limited)
OUTPUT_PAPERS = "papers.csv"
OUTPUT_ORGS = "organizations_summary.csv"

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

headers = {}
if API_KEY:
    headers["x-api-key"] = API_KEY

# Compute cutoff year (last 10 years)
CURRENT_YEAR = datetime.now().year
YEAR_CUTOFF = CURRENT_YEAR - 10

# ==========================
# FUNCTION: Fetch Papers
# ==========================

def fetch_papers():
    all_papers = []
    offset = 0

    while offset < MAX_PAPERS:
        params = {
            "query": QUERY,
            "limit": LIMIT_PER_REQUEST,
            "offset": offset,
            "fields": FIELDS
        }

        try:
            response = requests.get(BASE_URL, headers=headers, params=params, timeout=30)
            
            if response.status_code == 429:
                print("Rate limit hit. Waiting 10 seconds...")
                time.sleep(10)
                continue

            response.raise_for_status()
            data = response.json()

            papers = data.get("data", [])
            if not papers:
                break

            # Filter papers by year and citation count
            filtered_papers = [
                p for p in papers
                if p.get("year") and p["year"] >= YEAR_CUTOFF
                and p.get("citationCount", 0) > 1
            ]

            all_papers.extend(filtered_papers)
            offset += LIMIT_PER_REQUEST

            print(f"Collected {len(all_papers)} papers meeting criteria so far...")
            time.sleep(REQUEST_DELAY)

        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)

    return all_papers


# ==========================
# FUNCTION: Extract Organizations
# ==========================

def process_papers(papers):
    rows = []
    org_counter = Counter()

    for paper in tqdm(papers):
        title = paper.get("title", "")
        year = paper.get("year", "")
        abstract = paper.get("abstract", "")
        citation_count = paper.get("citationCount", 0)
        external_ids = paper.get("externalIds", {})
        doi = external_ids.get("DOI", "")

        authors = paper.get("authors", [])
        affiliations_list = []

        for author in authors:
            affiliations = author.get("affiliations", [])
            for aff in affiliations:
                org_counter[aff] += 1
                affiliations_list.append(aff)

        rows.append({
            "title": title,
            "year": year,
            "abstract": abstract,
            "citation_count": citation_count,
            "doi": doi,
            "affiliations": "; ".join(set(affiliations_list))
        })

    return rows, org_counter


# ==========================
# MAIN EXECUTION
# ==========================

if __name__ == "__main__":

    print("Starting large-scale PLEXOS paper scan (last 10 years, >1 citation)...")
    papers = fetch_papers()

    print(f"\nTotal papers retrieved meeting criteria: {len(papers)}")

    print("Processing affiliations, abstracts, citations, and DOI...")
    paper_rows, org_counter = process_papers(papers)

    # Save detailed paper data
    df_papers = pd.DataFrame(paper_rows)
    df_papers.to_csv(OUTPUT_PAPERS, index=False)

    # Save organization summary
    df_orgs = pd.DataFrame(
        org_counter.items(),
        columns=["organization", "mention_count"]
    ).sort_values(by="mention_count", ascending=False)

    df_orgs.to_csv(OUTPUT_ORGS, index=False)

    print("\nDone!")
    print(f"Papers saved to: {OUTPUT_PAPERS}")
    print(f"Organization summary saved to: {OUTPUT_ORGS}")
