"""keyword-based topic classification and stratified sampling for excavate subset."""

import json
import random
from collections import Counter
from pathlib import Path

from .corpus import load_corpus


def classify_abstract(abstract: dict, topic_keywords: dict[str, list[str]]) -> str:
    """assign primary topic based on keyword matching in title + abstract text."""
    haystack = (abstract["title"] + " " + abstract["abstract_text"]).lower()
    scores = {}
    for topic, keywords in topic_keywords.items():
        score = sum(1 for kw in keywords if kw.lower() in haystack)
        if score > 0:
            scores[topic] = score
    if not scores:
        return "other"
    return max(scores, key=scores.get)


def classify_all(
    abstracts: list[dict], topic_keywords: dict[str, list[str]] | None = None
) -> dict[str, list[dict]]:
    """classify all abstracts, return topic -> abstracts mapping.

    if topic_keywords is None or empty, all abstracts go into a single "all" bucket.
    """
    if not topic_keywords:
        return {"all": list(abstracts)}
    buckets: dict[str, list[dict]] = {}
    for a in abstracts:
        topic = classify_abstract(a, topic_keywords)
        buckets.setdefault(topic, []).append(a)
    return buckets


def stratified_sample(
    abstracts: list[dict],
    n: int = 30,
    seed: int = 42,
    topic_keywords: dict[str, list[str]] | None = None,
) -> list[dict]:
    """proportional stratified random sample across topic buckets.

    if topic_keywords is None or empty, falls back to pure random sample.
    """
    rng = random.Random(seed)

    if not topic_keywords:
        pool = list(abstracts)
        rng.shuffle(pool)
        return pool[:n]

    buckets = classify_all(abstracts, topic_keywords)
    total = len(abstracts)

    # compute allocation: proportional with floor of 1
    allocation = {}
    for topic, items in buckets.items():
        allocation[topic] = max(1, round(n * len(items) / total))

    # adjust to hit exact target n
    allocated = sum(allocation.values())
    while allocated > n:
        # shrink largest bucket
        largest = max(allocation, key=lambda t: allocation[t])
        if allocation[largest] > 1:
            allocation[largest] -= 1
            allocated -= 1
        else:
            break
    while allocated < n:
        # grow largest bucket that has room
        for topic in sorted(buckets, key=lambda t: len(buckets[t]), reverse=True):
            if allocation[topic] < len(buckets[topic]):
                allocation[topic] += 1
                allocated += 1
                if allocated >= n:
                    break

    # sample from each bucket
    selected = []
    for topic, count in allocation.items():
        pool = buckets[topic]
        sample = rng.sample(pool, min(count, len(pool)))
        selected.extend(sample)

    return selected


if __name__ == "__main__":
    from .config import load_conference
    import sys

    slug = sys.argv[1] if len(sys.argv) > 1 else "aahs2026"
    conf = load_conference(slug)
    corpus = load_corpus(conf["_index_path"])
    topic_keywords = conf.get("topics", {})

    # show topic distribution
    buckets = classify_all(corpus, topic_keywords)
    print("topic distribution:")
    for topic, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
        print(f"  {topic:25s} {len(items):3d} ({100*len(items)/len(corpus):.0f}%)")
    print(f"  {'TOTAL':25s} {len(corpus):3d}")

    # show stratified sample
    subset = stratified_sample(corpus, n=30, seed=42, topic_keywords=topic_keywords)
    print(f"\nstratified sample (n={len(subset)}):")
    subset_buckets = classify_all(subset, topic_keywords)
    for topic, items in sorted(subset_buckets.items(), key=lambda x: -len(x[1])):
        ids = [a["id"] for a in items]
        print(f"  {topic:25s} {len(items):2d}  {ids}")

    print(f"\nsubset IDs: {json.dumps([a['id'] for a in subset])}")
