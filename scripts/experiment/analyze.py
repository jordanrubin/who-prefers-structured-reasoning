#!/usr/bin/env python3
"""statistical analysis of experiment results.

loads expert + AI judge scores, computes paired comparisons,
bootstrap confidence intervals, and effect sizes.

usage:
    python -m scripts.experiment.analyze data/experiments/<conf>_YYYYMMDD_HHMMSS
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path


AI_DIMENSIONS = [
    "cross_abstract_inference",
    "epistemic_stratification",
    "falsifiability_yield",
    "corpus_coverage",
    "assumption_surfacing",
    "decision_readiness",
]

HUMAN_DIMENSIONS = [
    "didnt_know",
    "forward",
    "specific",
    "honest",
    "change",
]


def bootstrap_ci(values: list[float], n_boot: int = 10000, ci: float = 0.95, seed: int = 42) -> tuple[float, float, float]:
    """compute mean and bootstrap confidence interval."""
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        sample = [rng.choice(values) for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((1 - ci) / 2 * n_boot)]
    hi = means[int((1 + ci) / 2 * n_boot)]
    return sum(values) / n, lo, hi


def cohens_d(group_a: list[float], group_b: list[float]) -> float:
    """compute cohen's d effect size."""
    if not group_a or not group_b:
        return 0.0
    mean_a = sum(group_a) / len(group_a)
    mean_b = sum(group_b) / len(group_b)
    var_a = sum((x - mean_a) ** 2 for x in group_a) / max(1, len(group_a) - 1)
    var_b = sum((x - mean_b) ** 2 for x in group_b) / max(1, len(group_b) - 1)
    pooled_sd = ((var_a + var_b) / 2) ** 0.5
    if pooled_sd == 0:
        return 0.0
    return (mean_b - mean_a) / pooled_sd


def analyze_scores(scores: list[dict], dimensions: list[str], label: str) -> dict:
    """analyze scores for one evaluation type (human or AI)."""
    # group by condition
    by_condition = defaultdict(list)
    for s in scores:
        cond = s.get("condition", "unknown")
        by_condition[cond].append(s)

    results = {"label": label, "dimensions": {}, "composite": {}}

    for dim in dimensions:
        dim_results = {}
        for cond in ["condition_a", "condition_c"]:
            vals = [s[dim] for s in by_condition[cond] if dim in s]
            mean, lo, hi = bootstrap_ci(vals)
            dim_results[cond] = {"mean": round(mean, 2), "ci_lo": round(lo, 2), "ci_hi": round(hi, 2), "n": len(vals), "values": vals}

        # delta (C - A)
        vals_a = dim_results.get("condition_a", {}).get("values", [])
        vals_c = dim_results.get("condition_c", {}).get("values", [])
        delta = (sum(vals_c) / max(1, len(vals_c))) - (sum(vals_a) / max(1, len(vals_a))) if vals_a and vals_c else 0
        d = cohens_d(vals_a, vals_c)

        dim_results["delta"] = round(delta, 2)
        dim_results["cohens_d"] = round(d, 2)
        results["dimensions"][dim] = dim_results

    # composite (mean across all dimensions)
    for cond in ["condition_a", "condition_c"]:
        composites = []
        for s in by_condition[cond]:
            dim_scores = [s[dim] for dim in dimensions if dim in s]
            if dim_scores:
                composites.append(sum(dim_scores) / len(dim_scores))
        mean, lo, hi = bootstrap_ci(composites)
        results["composite"][cond] = {"mean": round(mean, 2), "ci_lo": round(lo, 2), "ci_hi": round(hi, 2), "n": len(composites)}

    comp_a = results["composite"].get("condition_a", {}).get("mean", 0)
    comp_c = results["composite"].get("condition_c", {}).get("mean", 0)
    results["composite"]["delta"] = round(comp_c - comp_a, 2)

    return results


def print_report(results: dict):
    """print a formatted console report."""
    label = results["label"]
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}\n")

    print(f"  {'dimension':<30} {'A':>6} {'C':>6} {'delta':>7} {'d':>6}")
    print(f"  {'-'*30} {'-'*6} {'-'*6} {'-'*7} {'-'*6}")

    for dim, data in results["dimensions"].items():
        a_mean = data.get("condition_a", {}).get("mean", 0)
        c_mean = data.get("condition_c", {}).get("mean", 0)
        delta = data["delta"]
        d = data["cohens_d"]
        marker = " **" if abs(d) >= 0.8 else " *" if abs(d) >= 0.5 else ""
        print(f"  {dim:<30} {a_mean:>6.2f} {c_mean:>6.2f} {delta:>+7.2f} {d:>6.2f}{marker}")

    comp = results["composite"]
    a_comp = comp.get("condition_a", {}).get("mean", 0)
    c_comp = comp.get("condition_c", {}).get("mean", 0)
    delta = comp["delta"]
    print(f"  {'-'*30} {'-'*6} {'-'*6} {'-'*7} {'-'*6}")
    print(f"  {'COMPOSITE':<30} {a_comp:>6.2f} {c_comp:>6.2f} {delta:>+7.2f}")
    print(f"\n  * medium effect (d≥0.5)  ** large effect (d≥0.8)")


def main():
    if len(sys.argv) < 2:
        print("usage: python -m scripts.experiment.analyze <experiment_dir>")
        sys.exit(1)

    exp_dir = Path(sys.argv[1])
    eval_dir = exp_dir / "evaluation"

    all_results = {}

    # AI judge scores
    judge_path = eval_dir / "judge_scores.json"
    if judge_path.exists():
        judge_scores = json.loads(judge_path.read_text())
        results = analyze_scores(judge_scores, AI_DIMENSIONS, "AI-JUDGED (6 dimensions)")
        print_report(results)
        all_results["ai_judge"] = results
    else:
        print("no AI judge scores found.")

    # human expert scores
    expert_path = eval_dir / "expert_scores.json"
    if expert_path.exists():
        expert_scores = json.loads(expert_path.read_text())
        results = analyze_scores(expert_scores, HUMAN_DIMENSIONS, "HUMAN-JUDGED (5 dimensions)")
        print_report(results)
        all_results["human_expert"] = results
    else:
        print("no human expert scores found.")

    # save analysis
    analysis_path = eval_dir / "analysis.json"
    analysis_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    print(f"\nanalysis saved to: {analysis_path}")


if __name__ == "__main__":
    main()
