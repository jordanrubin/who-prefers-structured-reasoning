#!/usr/bin/env python3
"""
1. clean up false-positive PubMed matches
2. download full-text PDFs from PMC via HTTPS
3. for non-PMC papers, try DOI redirect to publisher
"""

import json
import os
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent.parent / "data"
MATCHES_PATH = DATA_DIR / "pubmed_matches.json"
FULLTEXT_DIR = DATA_DIR / "fulltext"
HEADERS = {
    "User-Agent": "wpsr-research/1.0 (academic use)",
    "Accept": "application/pdf,text/xml,*/*",
}

# false positives: different papers matched by topic overlap
FALSE_POSITIVES = {
    "HS55",     # bariatric surgery ≠ weight loss medications
    "HSEP18",   # 2021 general OA review ≠ hand OA specific study
    "HSEP26",   # 2021 arthroscopic repair ≠ wafer + foveal combo
}


def download_pmc_pdf(pmcid: str, dest: Path) -> bool:
    """try to download PDF from PMC via HTTPS"""
    # PMC PDF URL pattern
    url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            # check if it's actually a PDF
            if resp.content[:5] == b'%PDF-':
                dest.write_bytes(resp.content)
                return True
            # sometimes it's HTML with the PDF embedded
            # try the main article page PDF link
    except Exception as e:
        print(f"    PDF download failed: {e}")

    # fallback: try efetch XML from PMC
    try:
        xml_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmcid}&rettype=full&retmode=xml"
        resp = requests.get(xml_url, headers=HEADERS, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 500:
            xml_dest = dest.with_suffix('.xml')
            xml_dest.write_bytes(resp.content)
            return True
    except Exception as e:
        print(f"    XML download failed: {e}")

    return False


def download_via_doi(doi: str, dest: Path) -> bool:
    """try to get PDF via DOI — works for some open access publishers"""
    if not doi:
        return False
    # try unpaywall for OA copy
    try:
        url = f"https://api.unpaywall.org/v2/{doi}?email=research@example.com"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            best = data.get("best_oa_location", {})
            if best:
                pdf_url = best.get("url_for_pdf") or best.get("url")
                if pdf_url:
                    print(f"    unpaywall found OA copy: {pdf_url[:70]}")
                    pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=60)
                    if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1000:
                        if pdf_resp.content[:5] == b'%PDF-':
                            dest.write_bytes(pdf_resp.content)
                            return True
    except Exception as e:
        print(f"    unpaywall failed: {e}")
    return False


def main():
    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)

    with open(MATCHES_PATH) as f:
        matches = json.load(f)

    # remove false positives
    original_count = len(matches)
    matches = [m for m in matches if m["aahs_id"] not in FALSE_POSITIVES]
    removed = original_count - len(matches)
    if removed:
        print(f"removed {removed} false positive matches")

    downloaded = 0
    already = 0

    for m in matches:
        aid = m["aahs_id"]
        pmid = m["pmid"]
        pmcid = m.get("pmcid", "")
        doi = m.get("doi", "")

        print(f"\n{aid} (PMID:{pmid}): {m['pubmed_title'][:60]}...")

        # check if already downloaded
        pdf_path = FULLTEXT_DIR / f"{aid}_{pmid}.pdf"
        xml_path = FULLTEXT_DIR / f"{aid}_{pmid}.xml"
        if pdf_path.exists() or xml_path.exists():
            print(f"    already downloaded")
            already += 1
            m["fulltext_downloaded"] = True
            m["fulltext_file"] = pdf_path.name if pdf_path.exists() else xml_path.name
            continue

        success = False

        # try PMC first
        if pmcid:
            print(f"    trying PMC ({pmcid})...")
            success = download_pmc_pdf(pmcid, pdf_path)
            time.sleep(0.5)

        # try DOI / unpaywall
        if not success and doi:
            print(f"    trying DOI ({doi})...")
            success = download_via_doi(doi, pdf_path)
            time.sleep(0.5)

        if success:
            downloaded += 1
            m["fulltext_downloaded"] = True
            m["fulltext_file"] = pdf_path.name if pdf_path.exists() else xml_path.name
            size_kb = (pdf_path.stat().st_size if pdf_path.exists() else xml_path.stat().st_size) / 1024
            print(f"    SUCCESS ({size_kb:.0f} KB)")
        else:
            print(f"    no open access full text available")
            m["fulltext_downloaded"] = False
            m["fulltext_file"] = ""

    # save cleaned matches
    with open(MATCHES_PATH, "w") as f:
        json.dump(matches, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"total matches: {len(matches)} (removed {removed} false positives)")
    print(f"downloaded: {downloaded} new, {already} already had")
    print(f"fulltext dir: {FULLTEXT_DIR}")

    # summary
    with_ft = sum(1 for m in matches if m["fulltext_downloaded"])
    without_ft = len(matches) - with_ft
    print(f"\nwith full text: {with_ft}")
    print(f"without (paywalled): {without_ft}")


if __name__ == "__main__":
    main()
