#!/usr/bin/env python3
"""
scrape all accepted papers from ICLR 2025 via the OpenReview API.

outputs data/iclr2025_index.json in the standardized index format.

usage:
    python scripts/scrapers/iclr2025.py [--limit N]
"""

import argparse
import json
import time
from pathlib import Path

import requests

VENUE_ID = "ICLR.cc/2025/Conference"
API_BASE = "https://api2.openreview.net"
DATA_DIR = Path(__file__).parent.parent.parent / "data"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (research-scraper; academic use)"
}

PAGE_SIZE = 200


def fetch_accepted_papers(limit: int | None = None) -> list[dict]:
    """fetch all accepted papers from the OpenReview API."""
    all_notes = []
    offset = 0

    while True:
        params = {
            "invitation": f"{VENUE_ID}/-/Submission",
            "content.venueid": VENUE_ID,
            "limit": PAGE_SIZE,
            "offset": offset,
        }
        print(f"  fetching offset={offset}...", end=" ", flush=True)
        resp = requests.get(f"{API_BASE}/notes", params=params, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        notes = data.get("notes", [])
        print(f"got {len(notes)}")

        if not notes:
            break

        all_notes.extend(notes)
        offset += len(notes)

        if limit and len(all_notes) >= limit:
            all_notes = all_notes[:limit]
            break

        time.sleep(0.5)

    return all_notes


def parse_venue_type(venue: str) -> str:
    """extract presentation type from venue string."""
    venue_lower = venue.lower()
    if "oral" in venue_lower:
        return "oral"
    if "spotlight" in venue_lower:
        return "spotlight"
    return "poster"


def note_to_abstract(note: dict, idx: int) -> dict:
    """convert an OpenReview note to standardized abstract index format."""
    content = note.get("content", {})

    title = content.get("title", {}).get("value", "")
    authors = content.get("authors", {}).get("value", [])
    abstract = content.get("abstract", {}).get("value", "")
    keywords = content.get("keywords", {}).get("value", [])
    venue = content.get("venue", {}).get("value", "")
    tldr = content.get("TLDR", {}).get("value", "")
    primary_area = content.get("primary_area", {}).get("value", "")

    paper_id = note.get("id", f"ICLR{idx}")
    forum_url = f"https://openreview.net/forum?id={paper_id}"

    return {
        "id": paper_id,
        "title": title,
        "authors": ", ".join(authors),
        "affiliations": "",
        "abstract_text": abstract,
        "sections": {"full_text": abstract},
        "url": forum_url,
        "type": parse_venue_type(venue),
        "keywords": keywords,
        "tldr": tldr,
        "primary_area": primary_area,
    }


def main():
    parser = argparse.ArgumentParser(description="Scrape ICLR 2025 accepted papers from OpenReview")
    parser.add_argument("--limit", type=int, default=None, help="max papers to fetch (default: all)")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"fetching ICLR 2025 accepted papers from OpenReview...")
    notes = fetch_accepted_papers(limit=args.limit)
    print(f"fetched {len(notes)} papers total")

    results = []
    for i, note in enumerate(notes, 1):
        abstract = note_to_abstract(note, i)
        if abstract["abstract_text"]:
            results.append(abstract)

    results.sort(key=lambda x: x["id"])

    from collections import Counter
    type_counts = Counter(a["type"] for a in results)
    print(f"\n{len(results)} papers with abstracts:")
    for t, n in type_counts.most_common():
        print(f"  {t}: {n}")

    index_path = DATA_DIR / "iclr2025_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nindex saved to: {index_path}")


if __name__ == "__main__":
    main()
