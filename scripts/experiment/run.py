#!/usr/bin/env python3
"""experiment orchestrator.

generates all prompt files and creates the experiment directory structure.
actual LLM calls happen via scripts.experiment.execute (Anthropic API) or by
hand / Claude Code Task agents — this just preps everything.

usage:
    python -m scripts.experiment.run --conference aahs2026 [--seed 42] [--subset-size 30] [--runs 3] [--judges 3]
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from .config import load_conference
from .corpus import load_corpus, format_corpus, estimate_tokens
from .subset import stratified_sample, classify_all
from .prompts import (
    naive_prompt,
    dimensionalize_prompt,
    handlize_prompt,
    inductify_prompt,
    negspace_prompt,
    excavate_prompt,
    human_scoring_instructions,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def create_experiment_dir(slug: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_dir = DATA_DIR / "experiments" / f"{slug}_{ts}"
    exp_dir.mkdir(parents=True, exist_ok=True)
    return exp_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conference", required=True, help="conference config slug (e.g. aahs2026)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--subset-size", type=int, default=30,
                        help="number of documents in the stratified excavate subset")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--judges", type=int, default=3,
                        help="number of independent judge evaluations per condition (default: 3)")
    args = parser.parse_args()

    # load conference config
    conf = load_conference(args.conference)
    c = conf["conference"]
    print(f"conference: {c['name']} ({c['abbreviation']}) {c['year']} {c['event']}")

    # load and format corpus
    corpus = load_corpus(conf["_index_path"])
    has_full_text = any(a.get("full_text", "").strip() for a in corpus)
    corpus_text = format_corpus(corpus, use_full_text=has_full_text)
    corpus_tokens = estimate_tokens(corpus_text)

    if has_full_text:
        print(f"corpus: {len(corpus)} studies (full text), ~{corpus_tokens:,} tokens")
    else:
        print(f"corpus: {len(corpus)} abstracts, ~{corpus_tokens:,} tokens")

    # stratified subset (clamp to corpus size)
    effective_subset = min(args.subset_size, len(corpus))
    topic_keywords = conf.get("topics", {})
    subset = stratified_sample(corpus, n=effective_subset, seed=args.seed, topic_keywords=topic_keywords)
    subset_ids = [a["id"] for a in subset]
    subset_text = format_corpus(corpus, ids=subset_ids, use_full_text=has_full_text)
    subset_tokens = estimate_tokens(subset_text)

    print(f"subset: {len(subset)} abstracts, ~{subset_tokens:,} tokens")
    print(f"topic distribution: {dict(sorted(((t, len(v)) for t, v in classify_all(subset, topic_keywords).items()), key=lambda x: -x[1]))}")

    # create experiment directory
    exp_dir = create_experiment_dir(conf["_slug"])
    print(f"\nexperiment dir: {exp_dir}")

    # save config
    config = {
        "conference": args.conference,
        "seed": args.seed,
        "subset_size": effective_subset,
        "num_runs": args.runs,
        "num_judges": args.judges,
        "model": "claude-opus-4-6",
        "corpus_size": len(corpus),
        "corpus_tokens_estimate": corpus_tokens,
        "subset_ids": subset_ids,
        "created": datetime.now().isoformat(),
    }
    (exp_dir / "config.json").write_text(json.dumps(config, indent=2))

    # save formatted corpus
    (exp_dir / "corpus_formatted.md").write_text(corpus_text)
    (exp_dir / "subset_ids.json").write_text(json.dumps(subset_ids, indent=2))

    # --- generate prompt files ---

    # condition A: the single-shot baseline prompt
    cond_a_dir = exp_dir / "condition_a"
    for run in range(1, args.runs + 1):
        run_dir = cond_a_dir / f"run_{run}"
        run_dir.mkdir(parents=True, exist_ok=True)
        prompt = naive_prompt(corpus_text, conf)
        (run_dir / "prompt.md").write_text(prompt)
        tokens = estimate_tokens(prompt)
        print(f"  condition_a/run_{run}/prompt.md ({tokens:,} tokens)")

    # condition C: the pipeline's operation prompts
    prompts_dir = exp_dir / "condition_c" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    # pre-processing: dimensionalize + handlize
    p = dimensionalize_prompt(conf)
    (prompts_dir / "step0a_dimensionalize.md").write_text(p)
    print(f"  condition_c/prompts/step0a_dimensionalize.md ({estimate_tokens(p):,} tokens)")

    p = handlize_prompt(corpus_text, conf)
    (prompts_dir / "step0b_handlize.md").write_text(p)
    print(f"  condition_c/prompts/step0b_handlize.md ({estimate_tokens(p):,} tokens)")

    # stage 1 parallel: inductify, negspace, excavate (x N)
    p = inductify_prompt(corpus_text, conf)
    (prompts_dir / "step1a_inductify.md").write_text(p)
    print(f"  condition_c/prompts/step1a_inductify.md ({estimate_tokens(p):,} tokens)")

    p = negspace_prompt(corpus_text, conf)
    (prompts_dir / "step1b_negspace.md").write_text(p)
    print(f"  condition_c/prompts/step1b_negspace.md ({estimate_tokens(p):,} tokens)")

    # individual excavate prompts for each subset abstract
    excavate_dir = prompts_dir / "excavate"
    excavate_dir.mkdir(parents=True, exist_ok=True)
    for a in subset:
        if has_full_text and a.get("full_text", "").strip():
            text = a["full_text"].strip()
        else:
            text = a["abstract_text"].strip()
        if not text or len(text) < 20:
            text = a["title"]
        p = excavate_prompt(text, a["id"], conf)
        (excavate_dir / f"{a['id']}.md").write_text(p)
    print(f"  condition_c/prompts/excavate/ ({len(subset)} individual prompts)")

    # stage 2: antithesize (generated after excavate outputs exist — placeholder)
    (prompts_dir / "step2_antithesize_TEMPLATE.md").write_text(
        "# antithesize prompt template\n\n"
        "this prompt is generated after the excavate outputs are collected.\n"
        "see prompts.antithesize_prompt(excavate_outputs, conf)\n"
    )

    # stage 3: final synthesis (generated after all operation outputs exist — placeholder)
    (prompts_dir / "step3_final_TEMPLATE.md").write_text(
        "# final synthesis prompt template\n\n"
        "this prompt is generated after all operation outputs are collected.\n"
        "it uses the SAME baseline prompt as condition A, but with the operation outputs prepended.\n"
        "see prompts.synthesize_with_skills_prompt(skill_outputs, corpus_text, conf)\n"
    )

    # create run directories for condition C
    for run in range(1, args.runs + 1):
        (exp_dir / "condition_c" / f"run_{run}").mkdir(parents=True, exist_ok=True)

    # evaluation directory
    eval_dir = exp_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "human_scoring_instructions.md").write_text(human_scoring_instructions(conf))
    for j in range(1, args.judges + 1):
        (eval_dir / f"judge_{j}").mkdir(parents=True, exist_ok=True)
    print(f"  evaluation: {args.judges} judge runs per condition")

    # token budget report
    print(f"\n{'='*60}")
    print("token budget estimate:")
    print(f"  corpus:                  ~{corpus_tokens:>8,}")
    print(f"  subset ({effective_subset}):             ~{subset_tokens:>8,}")
    print(f"  ---")
    print(f"  condition A total:       ~{corpus_tokens + 1000:>8,}")
    print(f"  condition C:")
    print(f"    inductify call:        ~{corpus_tokens + 1500:>8,}")
    print(f"    negspace call:         ~{corpus_tokens + 1500:>8,}")
    print(f"    excavate (per doc):    ~{500:>8,}")
    print(f"    antithesize:           ~{15000:>8,}  (estimated from {effective_subset} excavations)")
    print(f"    final synthesis:       ~{'???':>8}  (depends on intermediate sizes)")
    print(f"\nready. execute the operation prompts via scripts.experiment.execute or by hand.")
    print(f"prompts are in: {exp_dir}")


if __name__ == "__main__":
    main()
