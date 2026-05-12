#!/usr/bin/env python3
"""run the 6-dimension AI judge on the outputs of an experiment.

reads condition A (baseline) and condition C (pipeline) outputs from an
experiment directory created by `scripts.experiment.run` and executed by
`scripts.experiment.execute` (or by hand), then scores each with N independent
judge instances and writes per-eval JSON plus an aggregated `judge_scores.json`
in the format consumed by `scripts.experiment.analyze`.

usage:
    export ANTHROPIC_API_KEY=...
    python3 scripts/run_ai_judge.py \
        --experiment-dir data/experiments/aahs2026_YYYYMMDD_HHMMSS \
        --run 1 --n-evals 3

requires: ANTHROPIC_API_KEY env var, the `anthropic` package.

note: this is the convenience runner used for the paper's AI-judge evaluation.
`scripts.experiment.run` also emits standalone `judge_*_prompt.md` files that
can instead be fed to any judge (e.g. a separate Claude Code Task agent, or a
non-Anthropic model for the cross-model replication).
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.experiment.config import load_conference
from scripts.experiment.prompts import judge_prompt

DIM_KEYS = [
    "cross_abstract_inference",
    "epistemic_stratification",
    "falsifiability_yield",
    "corpus_coverage",
    "assumption_surfacing",
    "decision_readiness",
]

DEFAULT_MODEL = "claude-opus-4-6"

# response file names written by scripts.experiment.execute
OUTPUT_FILES = {
    "a": "response.md",
    "c": "final_response.md",
}


def parse_scores(text: str) -> dict:
    """extract the six 1-5 dimension scores from a judge response.

    the judge prompt asks for, per dimension, a `score (integer 1-5)` line.
    we look for `score: N` first, then fall back to `N/5`.
    """
    scores_list = re.findall(r"[Ss]core[:\s*]+(\d)", text)
    if len(scores_list) < 6:
        scores_list = re.findall(r"(\d)\s*/\s*5", text)
    if len(scores_list) < 6:
        raise ValueError(
            f"could not parse 6 dimension scores from judge response "
            f"(found {len(scores_list)})"
        )
    return {key: int(scores_list[i]) for i, key in enumerate(DIM_KEYS)}


def call_judge(client, model: str, prompt: str, max_retries: int = 5) -> str:
    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text
        except Exception as e:  # noqa: BLE001 - retry on transient API errors
            transient = any(t in str(e).lower() for t in ("rate", "429", "529", "overloaded"))
            if transient and attempt < max_retries - 1:
                wait = 60 * (attempt + 1)
                print(f"    transient error, retrying in {wait}s: {e}")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("unreachable")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--experiment-dir", required=True, type=Path)
    p.add_argument("--run", type=int, default=1)
    p.add_argument("--n-evals", type=int, default=3, help="independent judge instances per condition")
    p.add_argument("--conditions", nargs="+", default=["a", "c"], choices=["a", "c"])
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args()

    import anthropic

    exp_dir: Path = args.experiment_dir
    config = json.loads((exp_dir / "config.json").read_text())
    conf = load_conference(config["conference"])
    corpus_text = (exp_dir / "corpus_formatted.md").read_text()

    client = anthropic.Anthropic()
    eval_dir = exp_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)

    aggregated: list[dict] = []
    for cond in args.conditions:
        cond_dir = exp_dir / f"condition_{cond}" / f"run_{args.run}"
        output_path = cond_dir / OUTPUT_FILES[cond]
        if not output_path.exists():
            print(f"skipping condition {cond}: {output_path} not found")
            continue
        output_text = output_path.read_text()
        prompt = judge_prompt(output_text, corpus_text, conf)

        for i in range(1, args.n_evals + 1):
            print(f"[condition_{cond} run {args.run}] judge eval {i}/{args.n_evals}...")
            response_text = call_judge(client, args.model, prompt)
            tag = f"judge_{cond}_run{args.run}_eval{i}"
            (eval_dir / f"{tag}_raw.md").write_text(response_text)
            scores = parse_scores(response_text)
            composite = round(sum(scores.values()) / len(scores), 1)
            fabrication = []
            m = re.search(r"fabricat[^\n]*\n(.*)", response_text, re.IGNORECASE | re.DOTALL)
            if m:
                fabrication = [ln.strip(" -*\t") for ln in m.group(1).splitlines() if ln.strip(" -*\t")][:20]
            (eval_dir / f"{tag}.json").write_text(json.dumps({
                "condition": f"condition_{cond}",
                "run": args.run,
                "eval": i,
                "scores": scores,
                "composite": composite,
                "possible_fabrications": fabrication,
                "model": args.model,
            }, indent=2))
            aggregated.append({
                "condition": f"condition_{cond}",
                "run": args.run,
                "eval": i,
                **scores,
                "composite": composite,
            })
            print(f"    composite={composite} scores={scores}")
            time.sleep(3)

    # merge into any existing judge_scores.json (so multiple runs accumulate)
    scores_path = eval_dir / "judge_scores.json"
    existing: list[dict] = []
    if scores_path.exists():
        try:
            existing = json.loads(scores_path.read_text())
        except json.JSONDecodeError:
            existing = []
    # drop any prior entries for the (condition, run, eval) tuples we just wrote
    new_keys = {(s["condition"], s["run"], s["eval"]) for s in aggregated}
    merged = [s for s in existing if (s.get("condition"), s.get("run"), s.get("eval")) not in new_keys]
    merged.extend(aggregated)
    scores_path.write_text(json.dumps(merged, indent=2))
    print(f"\nwrote {len(aggregated)} new eval(s) -> {scores_path} ({len(merged)} total)")
    print("next: python -m scripts.experiment.analyze " + str(exp_dir))


if __name__ == "__main__":
    main()
