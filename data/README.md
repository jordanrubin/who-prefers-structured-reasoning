# Data

**The corpora are not redistributed in this repository.** Rebuild them with the
scrapers in [`../scripts/scrapers/`](../scripts/scrapers/), or drop your own
corpus here in the same format.

A corpus is a single JSON file — an array of document objects — placed at
`data/<slug>_index.json`. The required schema (id, title, authors, affiliations,
abstract_text, sections, url, type) is documented in
[`../scripts/scrapers/README.md`](../scripts/scrapers/README.md). The
`conferences/<slug>.toml` config's `index_path` points at this file.

## The three paper corpora

| Corpus | Domain | *n* | How to rebuild |
|---|---|---|---|
| ICLR 2025 oral abstracts | machine learning | 213 | `python scripts/scrapers/iclr2025.py` → `data/iclr2025_index.json`; the pipeline uses the `type == "oral"` subset (see `conferences/iclr2025.toml`): `python -c "import json; d=json.load(open('data/iclr2025_index.json')); json.dump([x for x in d if x['type']=='oral'], open('data/iclr2025_oral_index.json','w'), indent=2)"` |
| AAHS 2026 podiums + ePosters | hand surgery | 218 | `python scripts/scrapers/aahs2026.py` → `data/aahs2026_index.json` (also writes per-abstract files under `data/abstracts/` and `data/eposters/`). Optional: `python scripts/download_fulltext.py` + `python scripts/pubmed_crossref.py` for PubMed/Crossref cross-references. |
| AUSA 2025 news / policy articles | defense policy | 327 | `python scripts/scrapers/ausa2025_news.py` → `data/ausa2025_news_index.json` |

Scraper output and any corpus index files placed here are gitignored.

Corpus contents are © their original authors and publishers. The scrapers fetch
from public conference programs, OpenReview, and news pages; respect those
sites' terms when running them.
