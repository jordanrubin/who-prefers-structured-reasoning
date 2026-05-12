"""load and validate conference config from TOML."""

import json
import tomllib
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFERENCES_DIR = REPO_ROOT / "conferences"


def load_conference(slug: str) -> dict:
    """load conference config and compute derived corpus metadata.

    returns the raw TOML dict plus computed keys:
        _slug           — the conference slug
        _corpus_size    — total number of abstracts
        _type_counts    — Counter of abstract types (e.g. {"podium": 82, "eposter": 136})
        _index_path     — resolved Path to the index.json
    """
    path = CONFERENCES_DIR / f"{slug}.toml"
    if not path.exists():
        available = [p.stem for p in CONFERENCES_DIR.glob("*.toml") if p.stem != "example"]
        raise FileNotFoundError(
            f"conference config not found: {path}\n"
            f"available: {', '.join(available) or '(none)'}"
        )

    with open(path, "rb") as f:
        conf = tomllib.load(f)

    # validate required sections
    for section in ("conference", "corpus", "domain"):
        if section not in conf:
            raise ValueError(f"missing required section [{section}] in {path}")

    for key in ("name", "abbreviation", "year", "event"):
        if key not in conf["conference"]:
            raise ValueError(f"missing conference.{key} in {path}")

    if "index_path" not in conf["corpus"]:
        raise ValueError(f"missing corpus.index_path in {path}")

    if "field" not in conf["domain"]:
        raise ValueError(f"missing domain.field in {path}")

    # resolve index path and compute corpus metadata
    index_path = REPO_ROOT / conf["corpus"]["index_path"]
    conf["_index_path"] = index_path
    conf["_slug"] = slug

    if index_path.exists():
        with open(index_path) as f:
            abstracts = json.load(f)
        conf["_corpus_size"] = len(abstracts)
        conf["_type_counts"] = dict(Counter(a.get("type", "unknown") for a in abstracts))
    else:
        conf["_corpus_size"] = 0
        conf["_type_counts"] = {}

    # default topics to empty dict (triggers pure random sampling)
    conf.setdefault("topics", {})

    return conf
