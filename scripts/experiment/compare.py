#!/usr/bin/env python3
"""pairwise comparison of synthesis outputs across conditions.

computes text similarity, citation analysis, structural metrics,
emphasis patterns, decision artifacts, section alignment, and
claim novelty between condition A (naive) and condition C
(skill-augmented) responses.

usage:
    # single experiment (auto-discovers pairs)
    python3 -m scripts.experiment.compare data/experiments/<conf>_YYYYMMDD_HHMMSS

    # multiple experiments (aggregate)
    python3 -m scripts.experiment.compare data/experiments/dir1 data/experiments/dir2

    # explicit file pair
    python3 -m scripts.experiment.compare --files response_a.md response_c.md
"""

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path


# --- regex patterns ---

RE_CAUSAL = re.compile(
    r'\b(drives?|increases?|reduces?|implies?|predicts?|leads?\b.*?\bto'
    r'|causes?|enables?|prevents?|promotes?|inhibits?|attenuates?'
    r'|correlates?|exacerbates?|mediates?|modulates?)\b', re.I
)
RE_MODALITY = re.compile(
    r'\b(should|must|recommend(?:ed|s|ing)?|avoid(?:ed|s|ing)?'
    r'|consider(?:ed|s|ing)?|advise[ds]?|prefer(?:red|s)?'
    r'|warrant(?:ed|s)?|necessitat(?:es?|ing))\b', re.I
)
RE_UNCERTAINTY = re.compile(
    r'\b(confound(?:ed|ing|s|er)?|selection bias|underpowered'
    r'|external validity|heterogene(?:ity|ous)|bias(?:ed)?'
    r'|limitation(?:s)?|generalizab(?:le|ility)|small sample'
    r'|retrospective|single.center|lack(?:s|ed|ing)?\s+(?:of\s+)?(?:power|data|evidence)'
    r'|caution)\b', re.I
)
RE_COUNTERFACTUAL = re.compile(
    r'\b(however|on the other hand|failure mode|tradeoff|trade-off'
    r'|whereas|although|conversely|nonetheless|nevertheless'
    r'|alternatively|caveat|tension|complicat(?:es?|ed|ing)'
    r'|contradict(?:s|ed|ing)?|paradox(?:ical)?)\b', re.I
)
RE_THRESHOLD = re.compile(
    r'(?:[><=≥≤]\s*\d+(?:\.\d+)?'
    r'|\d+(?:\.\d+)?\s*(?:[><=≥≤%]|(?:[-–]\s*\d))'
    r'|\d+(?:\.\d+)?\s*(?:days?|weeks?|months?|years?|mm|cm|mg|ml|kg|hours?|minutes?)'
    r'|\b(?:p|P)\s*[<>=]\s*0?\.\d+)', re.I
)
RE_CITATION = re.compile(r'\b(?:HSEP?\d+|(?=[A-Za-z]*\d)[A-Za-z0-9]{10})\b')
RE_HEADING = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

STOPWORDS = frozenset(
    'a an the and or but in on of to for with by at from is are was were '
    'be been being have has had do does did will would shall should may might '
    'can could this that these those it its as not no nor'.split()
)


# --- primitives ---

def tokenize(text: str) -> list[str]:
    """lowercase, strip markdown formatting and punctuation, split to words."""
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)       # italic
    text = re.sub(r'#{1,6}\s+', '', text)             # headings
    text = re.sub(r'[^\w\s]', ' ', text)
    return [w for w in text.lower().split() if w]


def ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)}


def cosine_sim(tokens_a: list[str], tokens_b: list[str]) -> float:
    ca, cb = Counter(tokens_a), Counter(tokens_b)
    keys = set(ca) | set(cb)
    dot = sum(ca[k] * cb[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in ca.values()))
    mag_b = math.sqrt(sum(v * v for v in cb.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def extract_citations(text: str) -> set[str]:
    return set(RE_CITATION.findall(text))


def bold_phrases(text: str) -> set[str]:
    return {m.lower() for m in re.findall(r'\*\*([^*]+)\*\*', text)}


def structural_metrics(text: str) -> dict:
    words = text.split()
    word_count = len(words)
    sections = len(re.findall(r'^##\s+', text, re.MULTILINE))
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    mean_sent_len = sum(len(s.split()) for s in sentences) / max(1, len(sentences))
    tokens = tokenize(text)
    ttr = len(set(tokens)) / max(1, len(tokens))
    return {
        "word_count": word_count,
        "sections": sections,
        "lexical_diversity": round(ttr, 3),
        "mean_sentence_length": round(mean_sent_len, 1),
    }


# --- decision artifacts ---

def decision_artifacts(text: str) -> dict:
    """count decision-relevant language patterns."""
    return {
        "thresholds": len(RE_THRESHOLD.findall(text)),
        "causal_verbs": len(RE_CAUSAL.findall(text)),
        "modality": len(RE_MODALITY.findall(text)),
        "uncertainty": len(RE_UNCERTAINTY.findall(text)),
        "counterfactual": len(RE_COUNTERFACTUAL.findall(text)),
    }


# --- section alignment ---

def extract_headings(text: str) -> list[str]:
    """extract markdown headings, normalized lowercase."""
    return [m[1].strip().lower() for m in RE_HEADING.finditer(text)]


def kendall_tau(seq_a: list[str], seq_b: list[str]) -> float:
    """kendall tau on shared elements (1 = same order, -1 = reversed, 0 = no shared)."""
    shared = [h for h in seq_a if h in set(seq_b)]
    if len(shared) < 2:
        return 0.0
    b_pos = {h: i for i, h in enumerate(seq_b)}
    b_ranks = [b_pos[h] for h in shared if h in b_pos]
    n = len(b_ranks)
    if n < 2:
        return 0.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            if b_ranks[i] < b_ranks[j]:
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else 0.0


def topic_transitions(headings: list[str]) -> int:
    """count consecutive heading pairs with no content-word overlap."""
    if len(headings) < 2:
        return 0
    transitions = 0
    for i in range(1, len(headings)):
        prev = set(headings[i - 1].split()) - STOPWORDS
        curr = set(headings[i].split()) - STOPWORDS
        if prev and curr and not (prev & curr):
            transitions += 1
    return transitions


def section_alignment(text_a: str, text_b: str) -> dict:
    ha, hb = extract_headings(text_a), extract_headings(text_b)
    return {
        "headings_a": len(ha),
        "headings_b": len(hb),
        "heading_jaccard": round(jaccard(set(ha), set(hb)), 3),
        "kendall_tau": round(kendall_tau(ha, hb), 3),
        "transitions_a": topic_transitions(ha),
        "transitions_b": topic_transitions(hb),
    }


# --- claim novelty ---

def split_sentences(text: str) -> list[str]:
    """split into sentences, strip markdown."""
    clean = re.sub(r'#{1,6}\s+', '', text)
    clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)
    clean = re.sub(r'\*([^*]+)\*', r'\1', clean)
    sents = re.split(r'(?<=[.!?])\s+', clean)
    return [s.strip() for s in sents if len(s.strip()) > 20]


def is_claim(sent: str) -> bool:
    return bool(RE_CAUSAL.search(sent) or RE_MODALITY.search(sent))


def has_evidence(sent: str) -> bool:
    return bool(RE_CITATION.search(sent))


def has_action(sent: str) -> bool:
    return bool(RE_MODALITY.search(sent))


def sentence_is_novel(sent: str, other_sents: list[str], threshold: float = 0.5) -> bool:
    """novel if no sentence in other text shares >threshold of content words."""
    words = set(tokenize(sent)) - STOPWORDS
    if not words:
        return True
    for other in other_sents:
        other_words = set(tokenize(other)) - STOPWORDS
        if other_words and len(words & other_words) / len(words) > threshold:
            return False
    return True


def claim_novelty(text_a: str, text_b: str) -> dict:
    """measure novel claims that are supported and/or action-linked."""
    sents_a = split_sentences(text_a)
    sents_b = split_sentences(text_b)
    claims_a = [s for s in sents_a if is_claim(s)]
    claims_b = [s for s in sents_b if is_claim(s)]

    novel_a = [s for s in claims_a if sentence_is_novel(s, sents_b)]
    novel_b = [s for s in claims_b if sentence_is_novel(s, sents_a)]

    novel_supported_a = [s for s in novel_a if has_evidence(s)]
    novel_supported_b = [s for s in novel_b if has_evidence(s)]
    novel_action_a = [s for s in novel_a if has_action(s)]
    novel_action_b = [s for s in novel_b if has_action(s)]

    # claim-to-evidence density: citations per claim
    cit_a = len(RE_CITATION.findall(text_a))
    cit_b = len(RE_CITATION.findall(text_b))
    ced_a = round(cit_a / max(1, len(claims_a)), 2)
    ced_b = round(cit_b / max(1, len(claims_b)), 2)

    return {
        "claims_a": len(claims_a),
        "claims_b": len(claims_b),
        "novel_claims_a": len(novel_a),
        "novel_claims_b": len(novel_b),
        "novel_supported_a": len(novel_supported_a),
        "novel_supported_b": len(novel_supported_b),
        "novel_action_a": len(novel_action_a),
        "novel_action_b": len(novel_action_b),
        "cite_per_claim_a": ced_a,
        "cite_per_claim_b": ced_b,
    }


# --- comparison ---

def compare_pair(text_a: str, text_b: str) -> dict:
    """compute all metrics for one A/C pair."""
    tok_a, tok_b = tokenize(text_a), tokenize(text_b)
    set_a, set_b = set(tok_a), set(tok_b)

    # text similarity
    similarity = {
        "cosine": round(cosine_sim(tok_a, tok_b), 3),
        "jaccard_unigram": round(jaccard(set_a, set_b), 3),
        "jaccard_bigram": round(jaccard(ngrams(tok_a, 2), ngrams(tok_b, 2)), 3),
        "jaccard_trigram": round(jaccard(ngrams(tok_a, 3), ngrams(tok_b, 3)), 3),
    }

    # citations
    cit_a, cit_b = extract_citations(text_a), extract_citations(text_b)
    wc_a = len(text_a.split())
    wc_b = len(text_b.split())
    citations = {
        "count_a": len(cit_a),
        "count_b": len(cit_b),
        "shared": len(cit_a & cit_b),
        "a_only": len(cit_a - cit_b),
        "c_only": len(cit_b - cit_a),
        "jaccard": round(jaccard(cit_a, cit_b), 3),
        "density_a": round(len(cit_a) / max(1, wc_a) * 1000, 1),
        "density_c": round(len(cit_b) / max(1, wc_b) * 1000, 1),
        "top_a_only": sorted(cit_a - cit_b)[:10],
        "top_c_only": sorted(cit_b - cit_a)[:10],
    }

    # structure
    struct_a = structural_metrics(text_a)
    struct_b = structural_metrics(text_b)
    structure = {
        "a": struct_a,
        "c": struct_b,
        "word_count_ratio": round(struct_b["word_count"] / max(1, struct_a["word_count"]), 2),
    }

    # emphasis
    bold_a, bold_b = bold_phrases(text_a), bold_phrases(text_b)
    emphasis = {
        "bold_count_a": len(bold_a),
        "bold_count_c": len(bold_b),
        "bold_jaccard": round(jaccard(bold_a, bold_b), 3),
    }

    # decision artifacts
    da_a = decision_artifacts(text_a)
    da_b = decision_artifacts(text_b)
    artifacts = {
        "a": da_a,
        "c": da_b,
    }

    # section alignment
    alignment = section_alignment(text_a, text_b)

    # claim novelty
    novelty = claim_novelty(text_a, text_b)

    return {
        "similarity": similarity,
        "citations": citations,
        "structure": structure,
        "emphasis": emphasis,
        "decision_artifacts": artifacts,
        "section_alignment": alignment,
        "claim_novelty": novelty,
    }


# --- discovery ---

def find_pairs(exp_dir: Path) -> list[tuple[Path, Path]]:
    """find all valid (A, C) response pairs in an experiment dir."""
    pairs = []
    for run_dir in sorted(exp_dir.glob("condition_a/run_*")):
        run_name = run_dir.name
        path_a = run_dir / "response.md"
        path_c = exp_dir / "condition_c" / run_name / "final_response.md"
        if path_a.exists() and path_c.exists():
            pairs.append((path_a, path_c))
    return pairs


# --- aggregation ---

AGGREGATE_KEYS = [
    ("similarity", "cosine"),
    ("similarity", "jaccard_unigram"),
    ("similarity", "jaccard_bigram"),
    ("similarity", "jaccard_trigram"),
    ("citations", "jaccard"),
    ("citations", "count_a"),
    ("citations", "count_b"),
    ("citations", "density_a"),
    ("citations", "density_c"),
    ("structure", "word_count_ratio"),
    ("emphasis", "bold_jaccard"),
    ("section_alignment", "heading_jaccard"),
    ("section_alignment", "kendall_tau"),
    ("claim_novelty", "novel_supported_a"),
    ("claim_novelty", "novel_supported_b"),
    ("claim_novelty", "novel_action_a"),
    ("claim_novelty", "novel_action_b"),
    ("claim_novelty", "cite_per_claim_a"),
    ("claim_novelty", "cite_per_claim_b"),
]


def aggregate(results: list[dict]) -> dict:
    """compute mean/min/max across pairs for key metrics."""
    agg = {}
    for section, key in AGGREGATE_KEYS:
        vals = []
        for r in results:
            v = r.get(section, {}).get(key)
            if v is not None and not isinstance(v, (list, dict)):
                vals.append(float(v))
        if vals:
            agg[f"{section}.{key}"] = {
                "mean": round(sum(vals) / len(vals), 3),
                "min": round(min(vals), 3),
                "max": round(max(vals), 3),
                "n": len(vals),
            }
    return agg


# --- output ---

def print_report(results: dict, label: str):
    """formatted console output for one pair."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    sim = results["similarity"]
    print(f"\n  TEXT SIMILARITY")
    print(f"  {'cosine similarity':<28} {sim['cosine']:>8.3f}")
    print(f"  {'jaccard (unigram)':<28} {sim['jaccard_unigram']:>8.3f}")
    print(f"  {'jaccard (bigram)':<28} {sim['jaccard_bigram']:>8.3f}")
    print(f"  {'jaccard (trigram)':<28} {sim['jaccard_trigram']:>8.3f}")

    cit = results["citations"]
    print(f"\n  CITATION ANALYSIS")
    print(f"  {'sources A':<28} {cit['count_a']:>8}")
    print(f"  {'sources C':<28} {cit['count_b']:>8}")
    print(f"  {'shared':<28} {cit['shared']:>8}")
    print(f"  {'A-only':<28} {cit['a_only']:>8}")
    print(f"  {'C-only':<28} {cit['c_only']:>8}")
    print(f"  {'citation jaccard':<28} {cit['jaccard']:>8.3f}")
    print(f"  {'density A (per 1k words)':<28} {cit['density_a']:>8.1f}")
    print(f"  {'density C (per 1k words)':<28} {cit['density_c']:>8.1f}")
    if cit["top_a_only"]:
        print(f"  A-only sources: {', '.join(cit['top_a_only'])}")
    if cit["top_c_only"]:
        print(f"  C-only sources: {', '.join(cit['top_c_only'])}")

    struct = results["structure"]
    sa, sc = struct["a"], struct["c"]
    print(f"\n  STRUCTURAL METRICS")
    print(f"  {'metric':<28} {'A':>8} {'C':>8}")
    print(f"  {'-'*28} {'-'*8} {'-'*8}")
    print(f"  {'word count':<28} {sa['word_count']:>8} {sc['word_count']:>8}")
    print(f"  {'sections':<28} {sa['sections']:>8} {sc['sections']:>8}")
    print(f"  {'lexical diversity':<28} {sa['lexical_diversity']:>8.3f} {sc['lexical_diversity']:>8.3f}")
    print(f"  {'mean sentence length':<28} {sa['mean_sentence_length']:>8.1f} {sc['mean_sentence_length']:>8.1f}")
    print(f"  {'word count ratio (C/A)':<28} {struct['word_count_ratio']:>8.2f}")

    emph = results["emphasis"]
    print(f"\n  EMPHASIS PATTERNS")
    print(f"  {'bold phrases A':<28} {emph['bold_count_a']:>8}")
    print(f"  {'bold phrases C':<28} {emph['bold_count_c']:>8}")
    print(f"  {'bold jaccard':<28} {emph['bold_jaccard']:>8.3f}")

    da = results["decision_artifacts"]
    daa, dac = da["a"], da["c"]
    print(f"\n  DECISION ARTIFACTS")
    print(f"  {'metric':<28} {'A':>8} {'C':>8} {'delta':>8}")
    print(f"  {'-'*28} {'-'*8} {'-'*8} {'-'*8}")
    for key in ["thresholds", "causal_verbs", "modality", "uncertainty", "counterfactual"]:
        d = dac[key] - daa[key]
        sign = "+" if d > 0 else ""
        print(f"  {key:<28} {daa[key]:>8} {dac[key]:>8} {sign + str(d):>8}")
    total_a = sum(daa.values())
    total_c = sum(dac.values())
    d = total_c - total_a
    sign = "+" if d > 0 else ""
    print(f"  {'TOTAL':<28} {total_a:>8} {total_c:>8} {sign + str(d):>8}")

    sa = results["section_alignment"]
    print(f"\n  SECTION ALIGNMENT")
    print(f"  {'heading jaccard':<28} {sa['heading_jaccard']:>8.3f}")
    print(f"  {'kendall tau (ordering)':<28} {sa['kendall_tau']:>8.3f}")
    print(f"  {'topic transitions A':<28} {sa['transitions_a']:>8}")
    print(f"  {'topic transitions C':<28} {sa['transitions_b']:>8}")

    nov = results["claim_novelty"]
    print(f"\n  CLAIM NOVELTY")
    print(f"  {'metric':<28} {'A':>8} {'C':>8}")
    print(f"  {'-'*28} {'-'*8} {'-'*8}")
    print(f"  {'total claims':<28} {nov['claims_a']:>8} {nov['claims_b']:>8}")
    print(f"  {'novel claims':<28} {nov['novel_claims_a']:>8} {nov['novel_claims_b']:>8}")
    print(f"  {'novel + supported':<28} {nov['novel_supported_a']:>8} {nov['novel_supported_b']:>8}")
    print(f"  {'novel + action-linked':<28} {nov['novel_action_a']:>8} {nov['novel_action_b']:>8}")
    print(f"  {'citations per claim':<28} {nov['cite_per_claim_a']:>8.2f} {nov['cite_per_claim_b']:>8.2f}")
    # ornamental ratio
    for side, label in [("a", "A"), ("b", "C")]:
        novel = nov[f"novel_claims_{side}"]
        supported = nov[f"novel_supported_{side}"]
        action = nov[f"novel_action_{side}"]
        meaningful = max(supported, action)
        if novel > 0:
            ornamental = novel - meaningful
            pct = round(100 * ornamental / novel)
            print(f"  {'ornamental % ' + label:<28} {pct:>7}%  ({ornamental}/{novel})")


def print_aggregate(agg: dict, n_pairs: int):
    """summary table across all pairs."""
    print(f"\n{'='*60}")
    print(f"  AGGREGATE COMPARISON ({n_pairs} pairs)")
    print(f"{'='*60}\n")
    print(f"  {'metric':<32} {'mean':>8} {'min':>8} {'max':>8}")
    print(f"  {'-'*32} {'-'*8} {'-'*8} {'-'*8}")
    for key, vals in agg.items():
        label = key.split(".", 1)[1].replace("_", " ")
        print(f"  {label:<32} {vals['mean']:>8.3f} {vals['min']:>8.3f} {vals['max']:>8.3f}")


# --- CLI ---

def main():
    args = sys.argv[1:]
    if not args:
        print("usage: python3 -m scripts.experiment.compare <exp_dir> [exp_dir2 ...]")
        print("       python3 -m scripts.experiment.compare --files <a.md> <c.md>")
        sys.exit(1)

    # explicit file pair mode
    if args[0] == "--files":
        if len(args) != 3:
            print("--files requires exactly two file paths")
            sys.exit(1)
        path_a, path_c = Path(args[1]), Path(args[2])
        text_a, text_c = path_a.read_text(), path_c.read_text()
        results = compare_pair(text_a, text_c)
        print_report(results, f"{path_a.name} vs {path_c.name}")
        out = path_a.parent / "comparison.json"
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\nsaved to: {out}")
        return

    # experiment directory mode
    exp_dirs = [Path(a) for a in args]
    all_results = []
    all_labels = []

    for exp_dir in exp_dirs:
        pairs = find_pairs(exp_dir)
        if not pairs:
            print(f"no valid A/C pairs found in {exp_dir}")
            continue
        for path_a, path_c in pairs:
            text_a, text_c = path_a.read_text(), path_c.read_text()
            results = compare_pair(text_a, text_c)
            run_name = path_a.parent.name
            label = f"{exp_dir.name} / {run_name}"
            print_report(results, label)
            all_results.append(results)
            all_labels.append(label)

    if not all_results:
        print("no valid pairs found in any experiment directory.")
        sys.exit(1)

    # save per-experiment comparison json
    for exp_dir in exp_dirs:
        eval_dir = exp_dir / "evaluation"
        eval_dir.mkdir(exist_ok=True)
        # save results belonging to this experiment
        exp_results = []
        for r, l in zip(all_results, all_labels):
            if l.startswith(exp_dir.name):
                exp_results.append({"label": l, **r})
        if exp_results:
            out = eval_dir / "comparison.json"
            out.write_text(json.dumps(exp_results, indent=2, ensure_ascii=False))
            print(f"\nsaved to: {out}")

    # aggregate if multiple pairs
    if len(all_results) > 1:
        agg = aggregate(all_results)
        print_aggregate(agg, len(all_results))
        # save aggregate to first experiment dir
        eval_dir = exp_dirs[0] / "evaluation"
        eval_dir.mkdir(exist_ok=True)
        agg_out = eval_dir / "comparison_aggregate.json"
        agg_out.write_text(json.dumps(agg, indent=2, ensure_ascii=False))
        print(f"\naggregate saved to: {agg_out}")


if __name__ == "__main__":
    main()
