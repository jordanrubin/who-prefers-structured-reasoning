# Conference Scrapers

Each conference needs a custom scraper because every conference site has different HTML. The scraper's job is to produce a standardized `index.json` that the experiment pipeline consumes.

## index.json Schema

The scraper must output a JSON array of objects. Required fields:

```json
[
  {
    "id": "HS1",
    "title": "Full Title of the Abstract",
    "authors": "Smith J, Doe A, ...",
    "affiliations": "University of Example, ...",
    "abstract_text": "Full text of the abstract...",
    "sections": {
      "Introduction": "...",
      "Methods": "...",
      "Results": "...",
      "Conclusions": "..."
    },
    "url": "https://conference-site.org/abstract/HS1",
    "type": "podium"
  }
]
```

### Field Details

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Unique identifier within the conference |
| `title` | yes | Abstract title |
| `authors` | yes | Author list as a single string |
| `affiliations` | yes | Institutional affiliations |
| `abstract_text` | yes | Full abstract text (concatenated if sectioned) |
| `sections` | yes | Parsed sections dict, or `{"full_text": "..."}` if unstructured |
| `url` | yes | Source URL |
| `type` | yes | Presentation type (e.g. "podium", "eposter", "poster", "oral") |

### Adding a New Conference

1. Write a scraper that outputs `data/{slug}_index.json`
2. Create `conferences/{slug}.toml` (see `conferences/example.toml`)
3. Run: `python -m scripts.experiment.run --conference {slug}`

### Reference Implementations

These build the three corpora used in the paper:

- `aahs2026.py` — American Association for Hand Surgery 2026 Annual Meeting. Fetches from `meeting.handsurgery.org`, caches raw HTML, parses with BeautifulSoup. (`../download_fulltext.py` and `../pubmed_crossref.py` cross-reference these abstracts against PubMed/Crossref for spot-checks; outputs land in `data/fulltext/` and `data/pubmed_matches.json`.)
- `iclr2025.py` — ICLR 2025 from the OpenReview API. Outputs `data/iclr2025_index.json` with a `type` field; the pipeline uses the `type == "oral"` subset (`data/iclr2025_oral_index.json`).
- `ausa2025_news.py` — Association of the U.S. Army 2025 news/policy articles. Paginates `ausa.org/news`, visits each article, filters to 2025.
