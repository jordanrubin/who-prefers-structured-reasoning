#!/usr/bin/env python3
"""
scrape AUSA news articles from 2025.

- paginates through https://www.ausa.org/news?page=N
- visits each article page for full text
- filters to articles published in 2025
- outputs data/ausa2025_news_index.json

usage:
    python3 scripts/scrapers/ausa2025_news.py [--max-pages 50]
"""

import argparse
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

NEWS_URL = "https://www.ausa.org/news"
BASE_URL = "https://www.ausa.org"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "ausa2025_news"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (research-scraper; academic use)"
}


def fetch_html(url: str, cache_name: str | None = None) -> str | None:
    """fetch a page, optionally caching to disk."""
    if cache_name:
        cache_path = RAW_DIR / f"{cache_name}.html"
        if cache_path.exists():
            return cache_path.read_text(encoding="utf-8")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        html = resp.text
        if cache_name:
            cache_path = RAW_DIR / f"{cache_name}.html"
            cache_path.write_text(html, encoding="utf-8")
        return html
    except requests.RequestException as e:
        print(f"  [error] {url} -> {e}")
        return None


def parse_news_listing(html: str) -> list[dict]:
    """parse a news listing page for article links and summaries."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []

    # find all links to /news/ articles
    seen = set()
    for a_tag in soup.find_all("a", href=re.compile(r"^/news/[a-z0-9]")):
        href = a_tag.get("href", "")
        if href in seen or href == "/news":
            continue

        title = a_tag.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # skip image-only links (duplicate of the text link)
        if a_tag.find("img") and not title:
            continue

        seen.add(href)
        full_url = BASE_URL + href
        slug = href.rstrip("/").split("/")[-1]

        articles.append({
            "url": full_url,
            "slug": slug,
            "title": title,
        })

    return articles


def parse_article_page(html: str) -> dict:
    """extract full text and metadata from a news article page."""
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "full_text": "",
        "published_time": "",
        "og_title": "",
        "og_description": "",
    }

    # extract metadata
    og_title = soup.find("meta", property="og:title")
    if og_title:
        result["og_title"] = og_title.get("content", "")

    og_desc = soup.find("meta", property="og:description")
    if og_desc:
        result["og_description"] = og_desc.get("content", "")

    pub_time = soup.find("meta", property="article:published_time")
    if pub_time:
        result["published_time"] = pub_time.get("content", "")

    og_type = soup.find("meta", property="og:type")
    if og_type:
        result["og_type"] = og_type.get("content", "")

    # extract article body text
    body = None
    for selector in [
        "div.field--name-body",
        "article .field--name-body",
        "div.node__content",
        "article",
    ]:
        body = soup.select_one(selector)
        if body:
            break

    if not body:
        main = soup.find("main") or soup.find("div", role="main")
        if main:
            body = main

    if body:
        for tag in body.find_all(["script", "style", "nav", "footer"]):
            tag.decompose()

        paragraphs = []
        for elem in body.find_all(["p", "h2", "h3", "h4", "blockquote"]):
            text = elem.get_text(strip=True)
            if text and len(text) > 10:
                paragraphs.append(text)

        result["full_text"] = "\n\n".join(paragraphs)

    return result


def is_year(published_time: str, year: int) -> bool:
    """check if a published_time string is from the given year."""
    if not published_time:
        return False
    return str(year) in published_time[:10]


def main():
    parser = argparse.ArgumentParser(description="Scrape AUSA news articles")
    parser.add_argument("--max-pages", type=int, default=80, help="max listing pages (default: 80)")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # step 1: collect article URLs from paginated listing
    print(f"fetching AUSA news listings...")
    all_articles = []
    consecutive_old = 0

    for page in range(0, args.max_pages):
        url = f"{NEWS_URL}?page={page}" if page > 0 else NEWS_URL
        print(f"  page {page}...", end=" ", flush=True)

        html = fetch_html(url, cache_name=f"listing_page_{page}")
        if not html:
            print("empty/error — stopping")
            break

        articles = parse_news_listing(html)
        if not articles:
            print("no articles — stopping")
            break

        print(f"found {len(articles)} links")
        all_articles.extend(articles)
        time.sleep(0.5)

    # deduplicate by URL
    seen_urls = set()
    unique_articles = []
    for art in all_articles:
        if art["url"] not in seen_urls:
            seen_urls.add(art["url"])
            unique_articles.append(art)

    print(f"\n{len(unique_articles)} unique article URLs collected")

    # step 2: visit each article for full text, filter by year
    results = []
    skipped_old = 0  # consecutive non-2025 after we've seen at least one 2025
    found_any_2025 = False
    total = len(unique_articles)

    for i, art in enumerate(unique_articles, 1):
        prefix = f"[{i}/{total}]"
        title_short = art["title"][:50] + "..." if len(art["title"]) > 50 else art["title"]
        print(f"{prefix} {title_short}", end=" ", flush=True)

        detail_html = fetch_html(art["url"], cache_name=art["slug"])
        if not detail_html:
            print("-> error")
            continue

        detail = parse_article_page(detail_html)
        pub_time = detail.get("published_time", "")

        # filter to 2025
        if not is_year(pub_time, 2025):
            if found_any_2025:
                skipped_old += 1
            print(f"-> skip ({pub_time[:10] if pub_time else 'no date'})")
            # stop if we've passed through 2025 and hit 30 consecutive non-2025
            if found_any_2025 and skipped_old > 30:
                print(f"\n  stopping: {skipped_old} consecutive non-2025 articles")
                break
            time.sleep(0.3)
            continue

        found_any_2025 = True
        skipped_old = 0

        full_text = detail.get("full_text", "")
        article_id = f"AUSA-N-{len(results)+1:03d}"

        record = {
            "id": article_id,
            "title": detail.get("og_title") or art["title"],
            "authors": "",  # AUSA news typically doesn't have bylines in metadata
            "affiliations": "Association of the United States Army",
            "abstract_text": detail.get("og_description", ""),
            "full_text": full_text,
            "sections": {"full_text": full_text},
            "url": art["url"],
            "type": "article",
            "published_time": pub_time,
        }
        results.append(record)
        print(f"-> ok ({len(full_text)} chars)")

        time.sleep(0.5)

    # step 3: save index
    index_path = DATA_DIR / "ausa2025_news_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"done. {len(results)} news articles from 2025.")
    if results:
        avg_len = sum(len(r["full_text"]) for r in results) / len(results)
        print(f"  average text length: {avg_len:.0f} chars")
    print(f"  index saved to: {index_path}")


if __name__ == "__main__":
    main()
