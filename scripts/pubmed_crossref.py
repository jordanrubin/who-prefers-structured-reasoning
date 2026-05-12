#!/usr/bin/env python3
"""
cross-reference AAHS 2026 abstracts against PubMed/PMC.
for each abstract: search by title keywords + first author surname,
verify match quality (author overlap + title similarity),
and download full-text from PMC if open access.
"""

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from difflib import SequenceMatcher
from urllib.parse import quote_plus

import requests

DATA_DIR = Path(__file__).parent.parent / "data"
INDEX_PATH = DATA_DIR / "aahs2026_index.json"
FULLTEXT_DIR = DATA_DIR / "fulltext"
MATCHES_PATH = DATA_DIR / "pubmed_matches.json"

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PMC_OA_BASE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
HEADERS = {"User-Agent": "wpsr-research/1.0 (academic use)"}

# be polite to NCBI: max 3 requests/second without API key
REQUEST_DELAY = 0.4


def extract_surnames(authors_raw: str) -> list[str]:
    """pull last names from the messy author string"""
    # remove degree suffixes and superscripts
    cleaned = re.sub(r'\b(MD|PhD|DO|BS|BA|MS|MSc|MBA|MPH|MPHc|MBS|OTR|CHT|PA|RN|MSN|FNP|DPT|OTD|FACS)\b', '', authors_raw)
    cleaned = re.sub(r'\d+', '', cleaned)
    cleaned = re.sub(r'[()]', '', cleaned)
    # split on semicolons and commas (but commas within names are tricky)
    # try splitting on ; first, then on , if that doesn't work
    parts = re.split(r'[;]', cleaned)
    surnames = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # each part might have multiple comma-separated authors
        # or be "LastName FirstName, LastName FirstName"
        # heuristic: split on comma, take the first word of each chunk
        subparts = [s.strip() for s in part.split(',') if s.strip()]
        for sp in subparts:
            words = sp.split()
            if words:
                # surname is typically first token before comma or last before degree
                # but AAHS format is "FirstName LastName, Degree"
                # so first name of each author group
                # actually looking at the data: "Raysa Cabrejo, MD, Connor Arquette, MD"
                # after stripping degrees: "Raysa Cabrejo, , Connor Arquette, "
                # let's just grab multi-word names and take the last word as surname
                name_words = [w for w in words if len(w) > 1 and not w.startswith('(')]
                if len(name_words) >= 2:
                    surnames.append(name_words[-1])
                elif len(name_words) == 1:
                    surnames.append(name_words[0])
    return [s.lower().strip('.').strip(',') for s in surnames if len(s) > 1]


def title_similarity(t1: str, t2: str) -> float:
    """normalized similarity between two titles"""
    t1 = re.sub(r'[^\w\s]', '', t1.lower())
    t2 = re.sub(r'[^\w\s]', '', t2.lower())
    return SequenceMatcher(None, t1, t2).ratio()


def author_overlap(aahs_surnames: list[str], pubmed_authors: list[str]) -> float:
    """fraction of AAHS first/last author found in PubMed author list"""
    if not aahs_surnames or not pubmed_authors:
        return 0.0
    pm_lower = [a.lower() for a in pubmed_authors]
    # check first author and last author (most important)
    key_authors = [aahs_surnames[0]]
    if len(aahs_surnames) > 1:
        key_authors.append(aahs_surnames[-1])
    matches = sum(1 for a in key_authors if any(a in pm for pm in pm_lower))
    return matches / len(key_authors)


def search_pubmed(title: str, first_author_surname: str) -> list[str]:
    """search PubMed and return list of PMIDs"""
    # build query: title words + first author
    # use key title words (drop common ones)
    title_clean = re.sub(r'[^\w\s]', ' ', title)
    words = title_clean.split()
    # take first 6-8 meaningful words for the query
    stop = {'a', 'an', 'the', 'of', 'in', 'for', 'and', 'or', 'is', 'are',
            'with', 'to', 'from', 'by', 'on', 'at', 'vs', 'versus'}
    key_words = [w for w in words if w.lower() not in stop][:8]
    title_query = ' '.join(key_words)

    query = f'{title_query} AND {first_author_surname}[Author]'
    params = {
        'db': 'pubmed',
        'term': query,
        'retmax': 5,
        'retmode': 'json',
    }
    try:
        resp = requests.get(f'{NCBI_BASE}/esearch.fcgi', params=params,
                          headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get('esearchresult', {}).get('idlist', [])
    except Exception as e:
        print(f'    search error: {e}')
        return []


def fetch_pubmed_details(pmids: list[str]) -> list[dict]:
    """fetch article details for a list of PMIDs"""
    if not pmids:
        return []
    params = {
        'db': 'pubmed',
        'id': ','.join(pmids),
        'retmode': 'xml',
    }
    try:
        resp = requests.get(f'{NCBI_BASE}/efetch.fcgi', params=params,
                          headers=HEADERS, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        articles = []
        for article in root.findall('.//PubmedArticle'):
            info = {}
            # title
            title_el = article.find('.//ArticleTitle')
            info['title'] = title_el.text if title_el is not None and title_el.text else ''
            # authors
            authors = []
            for author in article.findall('.//Author'):
                last = author.find('LastName')
                if last is not None and last.text:
                    authors.append(last.text)
            info['authors'] = authors
            # PMID
            pmid_el = article.find('.//PMID')
            info['pmid'] = pmid_el.text if pmid_el is not None else ''
            # PMC ID
            for aid in article.findall('.//ArticleId'):
                if aid.get('IdType') == 'pmc':
                    info['pmcid'] = aid.text
            # DOI
            for aid in article.findall('.//ArticleId'):
                if aid.get('IdType') == 'doi':
                    info['doi'] = aid.text
            # journal
            journal_el = article.find('.//Journal/Title')
            info['journal'] = journal_el.text if journal_el is not None and journal_el.text else ''
            # year
            year_el = article.find('.//PubDate/Year')
            info['year'] = year_el.text if year_el is not None and year_el.text else ''
            # abstract
            abs_parts = article.findall('.//AbstractText')
            info['abstract'] = ' '.join(
                (a.text or '') for a in abs_parts
            )
            articles.append(info)
        return articles
    except Exception as e:
        print(f'    fetch error: {e}')
        return []


def check_pmc_fulltext(pmcid: str) -> str | None:
    """check if PMC article has open access full text, return PDF URL if available"""
    try:
        resp = requests.get(PMC_OA_BASE, params={'id': pmcid},
                          headers=HEADERS, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        # look for PDF link
        for link in root.findall('.//link'):
            fmt = link.get('format', '')
            href = link.get('href', '')
            if 'pdf' in fmt.lower() and href:
                return href
        # fallback: any link
        for link in root.findall('.//link'):
            href = link.get('href', '')
            if href:
                return href
    except Exception:
        pass
    return None


def download_fulltext(url: str, dest: Path) -> bool:
    """download a file from URL"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f'    download error: {e}')
        return False


def main():
    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)

    with open(INDEX_PATH) as f:
        abstracts = json.load(f)

    # load existing matches if resuming
    matches = []
    seen_ids = set()
    if MATCHES_PATH.exists():
        with open(MATCHES_PATH) as f:
            matches = json.load(f)
            seen_ids = {m['aahs_id'] for m in matches}

    total = len(abstracts)
    found = 0
    downloaded = 0

    print(f'cross-referencing {total} AAHS 2026 abstracts against PubMed...')
    if seen_ids:
        print(f'  resuming — {len(seen_ids)} already processed')
    print()

    for i, ab in enumerate(abstracts, 1):
        aid = ab['id']
        if aid in seen_ids:
            continue

        surnames = extract_surnames(ab['authors'])
        first_surname = surnames[0] if surnames else ''

        title_short = ab['title'][:65]
        print(f'[{i}/{total}] {aid}: {title_short}...', flush=True)

        if not first_surname:
            print(f'    no author surname extracted, skipping')
            continue

        # search pubmed
        pmids = search_pubmed(ab['title'], first_surname)
        time.sleep(REQUEST_DELAY)

        if not pmids:
            print(f'    no PubMed results')
            continue

        # fetch details
        articles = fetch_pubmed_details(pmids)
        time.sleep(REQUEST_DELAY)

        # find best match
        best = None
        best_score = 0
        for art in articles:
            t_sim = title_similarity(ab['title'], art['title'])
            a_ovl = author_overlap(surnames, art['authors'])
            # combined score: weight title heavily, require author match
            score = (t_sim * 0.6) + (a_ovl * 0.4)
            if score > best_score:
                best_score = score
                best = art
                best['_title_sim'] = t_sim
                best['_author_ovl'] = a_ovl

        if not best:
            print(f'    no match')
            continue

        t_sim = best['_title_sim']
        a_ovl = best['_author_ovl']

        # thresholds: title similarity > 0.5 AND at least first author matches
        if t_sim < 0.5 or a_ovl < 0.5:
            print(f'    weak match (title={t_sim:.2f}, author={a_ovl:.2f}) — skipping')
            print(f'    candidate: {best["title"][:70]}')
            continue

        print(f'    MATCH (title={t_sim:.2f}, author={a_ovl:.2f}): {best["title"][:65]}')
        print(f'    PMID: {best["pmid"]}, journal: {best.get("journal","")}, year: {best.get("year","")}')

        match_record = {
            'aahs_id': aid,
            'aahs_title': ab['title'],
            'pmid': best['pmid'],
            'pmcid': best.get('pmcid', ''),
            'doi': best.get('doi', ''),
            'pubmed_title': best['title'],
            'journal': best.get('journal', ''),
            'year': best.get('year', ''),
            'pubmed_authors': best['authors'],
            'title_similarity': round(t_sim, 3),
            'author_overlap': round(a_ovl, 3),
            'fulltext_downloaded': False,
            'fulltext_file': '',
        }

        # try to get full text from PMC
        pmcid = best.get('pmcid', '')
        if pmcid:
            print(f'    PMC: {pmcid} — checking open access...')
            pdf_url = check_pmc_fulltext(pmcid)
            time.sleep(REQUEST_DELAY)
            if pdf_url:
                ext = '.pdf' if 'pdf' in pdf_url.lower() else '.xml'
                dest = FULLTEXT_DIR / f'{aid}_{best["pmid"]}{ext}'
                print(f'    downloading full text...')
                if download_fulltext(pdf_url, dest):
                    match_record['fulltext_downloaded'] = True
                    match_record['fulltext_file'] = str(dest.name)
                    downloaded += 1
                    print(f'    saved: {dest.name}')
                time.sleep(REQUEST_DELAY)
            else:
                print(f'    no open access full text')
        else:
            print(f'    no PMC ID')

        matches.append(match_record)
        found += 1

        # save progress periodically
        if found % 5 == 0:
            with open(MATCHES_PATH, 'w') as f:
                json.dump(matches, f, indent=2, ensure_ascii=False)

    # final save
    with open(MATCHES_PATH, 'w') as f:
        json.dump(matches, f, indent=2, ensure_ascii=False)

    print(f'\n{"="*60}')
    print(f'done. {found} new matches found ({len(matches)} total).')
    print(f'{downloaded} full-text papers downloaded.')
    print(f'results saved to: {MATCHES_PATH}')


if __name__ == '__main__':
    main()
