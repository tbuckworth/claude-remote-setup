"""Resolve a citation identifier to metadata via Semantic Scholar / CrossRef.

Usage: uv run --python 3.12 --with httpx resolve_citation.py <identifier>

Identifier can be:
  --doi 10.xxxx/yyyy
  --arxiv 2401.12345
  --title "Paper Title"

Outputs JSON to stdout.
"""

import argparse
import json
import sys
import time

import httpx

S2_BASE = "https://api.semanticscholar.org/graph/v1/paper"
S2_FIELDS = "title,authors.name,authors.affiliations,year,abstract,url,externalIds,citationCount"
CROSSREF_BASE = "https://api.crossref.org/works"


def query_semantic_scholar(paper_id: str) -> dict | None:
    """Query Semantic Scholar API for paper metadata."""
    url = f"{S2_BASE}/{paper_id}"
    params = {"fields": S2_FIELDS}

    try:
        resp = httpx.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            external = data.get("externalIds", {}) or {}
            authors = []
            for a in (data.get("authors") or []):
                entry = {"name": a.get("name", "")}
                affiliations = a.get("affiliations") or []
                if affiliations:
                    entry["affiliations"] = affiliations
                authors.append(entry)
            return {
                "title": data.get("title", ""),
                "authors": authors,
                "year": data.get("year"),
                "abstract": data.get("abstract", ""),
                "url": data.get("url", ""),
                "doi": external.get("DOI", ""),
                "arxiv_id": external.get("ArXiv", ""),
                "citation_count": data.get("citationCount"),
                "source": "semantic_scholar",
            }
        elif resp.status_code == 429:
            print("Rate limited by Semantic Scholar, waiting...", file=sys.stderr)
            time.sleep(3)
            return query_semantic_scholar(paper_id)
    except httpx.TimeoutException:
        print("Semantic Scholar timeout", file=sys.stderr)

    return None


def query_crossref(identifier: str, is_title: bool = False) -> dict | None:
    """Query CrossRef API for paper metadata."""
    try:
        if is_title:
            url = CROSSREF_BASE
            params = {"query": identifier, "rows": 1}
        else:
            url = f"{CROSSREF_BASE}/{identifier}"
            params = {}

        resp = httpx.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if is_title:
                items = data.get("message", {}).get("items", [])
                if not items:
                    return None
                item = items[0]
            else:
                item = data.get("message", {})

            title_parts = item.get("title", [])
            title = title_parts[0] if title_parts else ""

            authors = []
            for a in item.get("author", []):
                name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                if name:
                    authors.append(name)

            year = None
            date_parts = item.get("published-print", item.get("published-online", {}))
            if date_parts and date_parts.get("date-parts"):
                year = date_parts["date-parts"][0][0]

            return {
                "title": title,
                "authors": authors,
                "year": year,
                "abstract": item.get("abstract", ""),
                "url": item.get("URL", ""),
                "doi": item.get("DOI", ""),
                "arxiv_id": "",
                "citation_count": item.get("is-referenced-by-count"),
                "source": "crossref",
            }
    except httpx.TimeoutException:
        print("CrossRef timeout", file=sys.stderr)

    return None


def resolve(doi: str = None, arxiv: str = None, title: str = None) -> dict:
    """Resolve a citation using available identifiers."""
    result = None

    # Try Semantic Scholar first
    if doi:
        result = query_semantic_scholar(f"DOI:{doi}")
    if not result and arxiv:
        result = query_semantic_scholar(f"ARXIV:{arxiv}")
    if not result and title:
        # S2 search endpoint
        try:
            resp = httpx.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": title, "limit": 1, "fields": S2_FIELDS},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    paper = data[0]
                    external = paper.get("externalIds", {}) or {}
                    authors = []
                    for a in (paper.get("authors") or []):
                        entry = {"name": a.get("name", "")}
                        affiliations = a.get("affiliations") or []
                        if affiliations:
                            entry["affiliations"] = affiliations
                        authors.append(entry)
                    result = {
                        "title": paper.get("title", ""),
                        "authors": authors,
                        "year": paper.get("year"),
                        "abstract": paper.get("abstract", ""),
                        "url": paper.get("url", ""),
                        "doi": external.get("DOI", ""),
                        "arxiv_id": external.get("ArXiv", ""),
                        "citation_count": paper.get("citationCount"),
                        "source": "semantic_scholar",
                    }
        except httpx.TimeoutException:
            pass

    # Fallback to CrossRef
    if not result:
        time.sleep(1.1)  # Rate limit respect
        if doi:
            result = query_crossref(doi)
        elif title:
            result = query_crossref(title, is_title=True)

    if not result:
        return {"error": "Could not resolve citation", "doi": doi, "arxiv": arxiv, "title": title}

    return result


def main():
    parser = argparse.ArgumentParser(description="Resolve citation metadata")
    parser.add_argument("--doi", help="DOI identifier")
    parser.add_argument("--arxiv", help="arXiv ID")
    parser.add_argument("--title", help="Paper title")
    args = parser.parse_args()

    if not any([args.doi, args.arxiv, args.title]):
        parser.error("At least one of --doi, --arxiv, or --title is required")

    result = resolve(doi=args.doi, arxiv=args.arxiv, title=args.title)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
