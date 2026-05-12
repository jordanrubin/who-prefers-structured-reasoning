"""load and format the abstract corpus for context injection."""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_corpus(index_path: Path | None = None) -> list[dict]:
    """load abstracts from an index.json file.

    if index_path is None, falls back to the legacy default for backwards compat.
    """
    if index_path is None:
        index_path = DATA_DIR / "aahs2026_index.json"
    with open(index_path) as f:
        return json.load(f)


def format_corpus(abstracts: list[dict], ids: list[str] | None = None, use_full_text: bool = False) -> str:
    """format abstracts as markdown for LLM context.
    compact: id, title, type, text. no authors/affiliations (saves tokens).
    if use_full_text=True and full_text is available, use it instead of abstract_text.
    """
    if ids:
        id_set = set(ids)
        abstracts = [a for a in abstracts if a["id"] in id_set]

    parts = []
    for a in abstracts:
        if use_full_text and a.get("full_text", "").strip():
            text = a["full_text"].strip()
        else:
            text = a["abstract_text"].strip()
        if not text or len(text) < 20:
            text = f"[abstract text unavailable — title only: {a['title']}]"
        parts.append(
            f"---\n"
            f"## {a['id']}: {a['title']}\n"
            f"**Type:** {a['type']}\n\n"
            f"{text}"
        )
    return "\n\n".join(parts)


def format_corpus_compact(abstracts: list[dict]) -> str:
    """ultra-compact: one line per abstract for token-constrained contexts."""
    lines = []
    for a in abstracts:
        text = a["abstract_text"].strip()
        if not text or len(text) < 20:
            continue
        # first 200 chars of abstract as preview
        preview = text[:200].replace("\n", " ")
        lines.append(f"[{a['id']}] {a['title']} | {preview}...")
    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """rough token estimate: ~1.33 tokens per word for english text."""
    return int(len(text.split()) * 1.33)


if __name__ == "__main__":
    corpus = load_corpus()
    formatted = format_corpus(corpus)
    tokens = estimate_tokens(formatted)
    print(f"loaded {len(corpus)} abstracts")
    print(f"formatted: {len(formatted):,} chars, ~{tokens:,} tokens")

    compact = format_corpus_compact(corpus)
    compact_tokens = estimate_tokens(compact)
    print(f"compact: {len(compact):,} chars, ~{compact_tokens:,} tokens")
