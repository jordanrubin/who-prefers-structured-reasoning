#!/usr/bin/env python3
"""interactive expert scoring CLI.

presents outputs blinded and in randomized order.
expert scores on 5 gut-level dimensions without having read the abstracts.

usage:
    python -m scripts.experiment.evaluate data/experiments/<conf>_YYYYMMDD_HHMMSS
"""

import json
import random
import sys
from pathlib import Path


DIMENSIONS = [
    ("didnt_know", '"I DIDN\'T KNOW THAT" — genuine surprise about the field'),
    ("forward", '"I\'D FORWARD THIS" — worth sharing with a colleague'),
    ("specific", '"THIS IS SPECIFIC" — unmistakably about this field right now'),
    ("honest", '"THIS IS HONEST" — calibrated, trustworthy, no BS detector'),
    ("change", '"I\'D CHANGE SOMETHING" — concrete behavior change prompted'),
]


def collect_scores(output_text: str, label: str) -> dict:
    """display output and collect 5-dimension scores from the expert."""
    print("\n" + "=" * 70)
    print(f"OUTPUT {label}")
    print("=" * 70)
    print()
    print(output_text[:10000])  # cap display at 10k chars
    if len(output_text) > 10000:
        print(f"\n... [{len(output_text) - 10000} more characters, see file for full text]")
    print()
    print("-" * 70)
    print("score 1-5 on each dimension (or 'q' to quit):\n")

    scores = {}
    for key, description in DIMENSIONS:
        while True:
            val = input(f"  {description}: ").strip()
            if val.lower() == "q":
                print("quitting.")
                sys.exit(0)
            try:
                score = int(val)
                if 1 <= score <= 5:
                    scores[key] = score
                    break
                else:
                    print("    (enter 1-5)")
            except ValueError:
                print("    (enter 1-5)")

    notes = input("\n  notes (optional, press enter to skip): ").strip()
    if notes:
        scores["notes"] = notes
    return scores


def main():
    if len(sys.argv) < 2:
        print("usage: python -m scripts.experiment.evaluate <experiment_dir>")
        sys.exit(1)

    exp_dir = Path(sys.argv[1])
    if not exp_dir.exists():
        print(f"experiment directory not found: {exp_dir}")
        sys.exit(1)

    eval_dir = exp_dir / "evaluation"
    eval_dir.mkdir(exist_ok=True)

    # collect all response files
    outputs = []
    for condition in ["condition_a", "condition_c"]:
        cond_dir = exp_dir / condition
        if not cond_dir.exists():
            continue
        for run_dir in sorted(cond_dir.iterdir()):
            if not run_dir.is_dir() or run_dir.name == "prompts":
                continue
            # look for response file
            for name in ["response.md", "final_response.md"]:
                resp_file = run_dir / name
                if resp_file.exists():
                    outputs.append({
                        "condition": condition,
                        "run": run_dir.name,
                        "file": str(resp_file),
                        "text": resp_file.read_text(encoding="utf-8"),
                    })
                    break

    if not outputs:
        print("no response files found. run the experiment first.")
        sys.exit(1)

    # load existing scores if resuming
    scores_path = eval_dir / "expert_scores.json"
    existing = []
    scored_keys = set()
    if scores_path.exists():
        existing = json.loads(scores_path.read_text())
        scored_keys = {(s["condition"], s["run"]) for s in existing}

    # filter out already-scored
    remaining = [o for o in outputs if (o["condition"], o["run"]) not in scored_keys]

    if not remaining:
        print("all outputs already scored.")
        sys.exit(0)

    # randomize presentation order (blind to condition)
    rng = random.Random(99)
    rng.shuffle(remaining)

    print(f"\n{len(remaining)} outputs to score ({len(existing)} already done)")
    print("outputs are presented in randomized order, condition labels hidden.\n")

    all_scores = list(existing)

    for i, output in enumerate(remaining, 1):
        label = f"{i}/{len(remaining)}"
        scores = collect_scores(output["text"], label)
        scores["condition"] = output["condition"]
        scores["run"] = output["run"]
        scores["file"] = output["file"]
        all_scores.append(scores)

        # save after each scoring
        scores_path.write_text(json.dumps(all_scores, indent=2, ensure_ascii=False))
        print(f"  saved. ({len(all_scores)} total scores)\n")

    print(f"\ndone. {len(all_scores)} scores saved to {scores_path}")


if __name__ == "__main__":
    main()
