#!/usr/bin/env python3
"""
scrape all abstracts from AAHS 2026 annual meeting
- regular abstracts: HS1-HS84 (missing 41, 75)
- eposters: HSEP1-HSEP138 (missing 28, 29)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://meeting.handsurgery.org/program/2026"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
ABSTRACTS_DIR = DATA_DIR / "abstracts"
EPOSTERS_DIR = DATA_DIR / "eposters"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (research-scraper; academic use)"
}

# build the full list of abstract IDs
REGULAR_IDS = [f"HS{i}" for i in range(1, 85) if i not in (41, 75)]
EPOSTER_IDS = [f"HSEP{i}" for i in range(1, 139) if i not in (28, 29)]


def fetch_page(abstract_id: str) -> str | None:
    """fetch and cache a single abstract page"""
    cache_path = RAW_DIR / f"{abstract_id}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    url = f"{BASE_URL}/{abstract_id}.cgi"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            print(f"  [skip] {abstract_id} -> 404")
            return None
        resp.raise_for_status()
        html = resp.text
        cache_path.write_text(html, encoding="utf-8")
        return html
    except requests.RequestException as e:
        print(f"  [error] {abstract_id} -> {e}")
        return None


def parse_abstract(html: str, abstract_id: str) -> dict | None:
    """extract structured data from an abstract page"""
    soup = BeautifulSoup(html, "html.parser")

    # the content lives inside div align="left"
    content_div = soup.find("div", align="left")
    if not content_div:
        return None

    # title is the first <b> tag after the <hr>
    hr = content_div.find("hr")
    if not hr:
        return None

    title_tag = hr.find_next("b")
    if not title_tag:
        return None
    title = title_tag.get_text(strip=True)

    # authors + affiliations: everything between the title <b> and the abstract body
    # authors are in the text right after the title <b>, before <i> (affiliations)
    # grab the raw HTML between first <hr> and second <hr>
    hrs = content_div.find_all("hr")
    if len(hrs) < 2:
        return None

    body_html = ""
    node = hrs[0].next_sibling
    while node and node != hrs[1]:
        if hasattr(node, "decode"):
            body_html += str(node)
        else:
            body_html += str(node)
        node = node.next_sibling

    # parse authors from the elements after title
    authors_raw = ""
    affil_raw = ""

    # find the <br> after title, then text until <i>
    title_b = hr.find_next("b")
    # walk siblings after the title <b>
    node = title_b.next_sibling
    author_parts = []
    while node:
        if hasattr(node, "name"):
            if node.name == "i":
                affil_raw = node.get_text(strip=True)
                break
            elif node.name == "br":
                pass
            elif node.name == "sup":
                author_parts.append(node.get_text())
            else:
                author_parts.append(node.get_text())
        else:
            text = str(node).strip()
            if text:
                author_parts.append(text)
        node = node.next_sibling

    authors_raw = "".join(author_parts).strip()
    # clean up superscript numbers and extra whitespace
    authors_clean = re.sub(r"\s+", " ", authors_raw).strip()

    # extract abstract text: everything after affiliations <i> up to second <hr>
    abstract_text = ""
    if affil_raw:
        affil_node = hr.find_next("i")
        if affil_node:
            node = affil_node.next_sibling
            text_parts = []
            while node and node != hrs[1]:
                if hasattr(node, "name") and node.name == "hr":
                    break
                if hasattr(node, "get_text"):
                    text_parts.append(node.get_text())
                else:
                    text_parts.append(str(node))
                node = node.next_sibling
            abstract_text = "".join(text_parts).strip()

    # try to parse sections (Introduction, Methods, Results, Conclusion)
    sections = {}
    # check if abstract has bold section headers
    section_pattern = re.compile(
        r"(Introduction|Background|Methods|Materials\s*(?:&|and)\s*Methods|Results|Conclusions?|Discussion|Purpose|Hypothesis|Objectives?)",
        re.IGNORECASE,
    )
    if section_pattern.search(abstract_text):
        current_section = "preamble"
        for line in re.split(r"\n+", abstract_text):
            match = section_pattern.match(line.strip())
            if match:
                current_section = match.group(1).strip()
            else:
                sections.setdefault(current_section, []).append(line)
        sections = {k: "\n".join(v).strip() for k, v in sections.items() if v}
    else:
        sections = {"full_text": abstract_text}

    # also extract from meta description for a clean version
    meta_desc = soup.find("meta", attrs={"name": "description"})
    meta_title = meta_desc["content"] if meta_desc else ""

    return {
        "id": abstract_id,
        "title": title,
        "authors": authors_clean,
        "affiliations": affil_raw,
        "abstract_text": abstract_text,
        "sections": sections,
        "url": f"{BASE_URL}/{abstract_id}.cgi",
        "type": "eposter" if abstract_id.startswith("HSEP") else "podium",
    }


def save_abstract(data: dict, out_dir: Path):
    """save abstract as both json and markdown"""
    aid = data["id"]

    # json
    json_path = out_dir / f"{aid}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # markdown
    md_path = out_dir / f"{aid}.md"
    md = f"# {data['title']}\n\n"
    md += f"**ID:** {data['id']}  \n"
    md += f"**Type:** {data['type']}  \n"
    md += f"**Authors:** {data['authors']}  \n"
    md += f"**Affiliations:** {data['affiliations']}  \n"
    md += f"**URL:** {data['url']}  \n\n"
    md += "---\n\n"
    md += data["abstract_text"] + "\n"
    md_path.write_text(md, encoding="utf-8")


def main():
    for d in (RAW_DIR, ABSTRACTS_DIR, EPOSTERS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    all_ids = REGULAR_IDS + EPOSTER_IDS
    total = len(all_ids)
    results = []
    errors = []

    print(f"scraping {total} abstracts from AAHS 2026...")
    print(f"  regular: {len(REGULAR_IDS)}, eposters: {len(EPOSTER_IDS)}")
    print()

    for i, aid in enumerate(all_ids, 1):
        prefix = f"[{i}/{total}]"
        print(f"{prefix} {aid}...", end=" ", flush=True)

        html = fetch_page(aid)
        if not html:
            errors.append(aid)
            continue

        data = parse_abstract(html, aid)
        if not data:
            print("parse failed")
            errors.append(aid)
            continue

        out_dir = EPOSTERS_DIR if aid.startswith("HSEP") else ABSTRACTS_DIR
        save_abstract(data, out_dir)
        results.append(data)

        title_short = data["title"][:60] + "..." if len(data["title"]) > 60 else data["title"]
        print(f"ok -> {title_short}")

        # polite delay between requests (skip if cached)
        cache_path = RAW_DIR / f"{aid}.html"
        if not cache_path.exists():
            time.sleep(0.5)

    # save master index
    index_path = DATA_DIR / "aahs2026_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"done. {len(results)}/{total} abstracts scraped successfully.")
    if errors:
        print(f"errors/skips ({len(errors)}): {errors}")
    print(f"index saved to: {index_path}")


if __name__ == "__main__":
    main()
