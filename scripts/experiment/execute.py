#!/usr/bin/env python3
"""execute experiment runs via Anthropic API.

automates the full condition A + condition C pipeline for specified runs
within an existing experiment directory (created by run.py).

usage (the --experiment-dir is one created by scripts.experiment.run):
    python3 -m scripts.experiment.execute \
        --experiment-dir data/experiments/aahs2026_YYYYMMDD_HHMMSS \
        --runs 2 3

    # run only condition A (faster, cheaper):
    python3 -m scripts.experiment.execute \
        --experiment-dir data/experiments/aahs2026_YYYYMMDD_HHMMSS \
        --runs 2 --condition a

    # use a cheaper model for intermediate operation steps:
    python3 -m scripts.experiment.execute \
        --experiment-dir data/experiments/aahs2026_YYYYMMDD_HHMMSS \
        --runs 2 3 --intermediate-model claude-sonnet-4-6

pipeline per run:
    condition A:  prompt.md → response.md → response.pdf
    condition C:
        1. [parallel] inductify, negspace, excavate batches (3-5 calls)
        2. condense excavate batches
        3. generate + run antithesize
        4. assemble + run final synthesis
        5. final_response.md → final_response.pdf
    post:
        6. strip title headers from all outputs
        7. generate judge prompts for this run

requires: ANTHROPIC_API_KEY env var, weasyprint, markdown packages.
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
import markdown as md_lib
import weasyprint

from .config import load_conference
from .prompts import (
    antithesize_prompt,
    judge_prompt,
    synthesize_with_skills_prompt,
)


DEFAULT_MODEL = "claude-opus-4-6"
MAX_TOKENS = 16384
EXCAVATE_BATCH_SIZE = 10

# suppress weasyprint warnings
import logging
logging.getLogger("weasyprint").setLevel(logging.ERROR)
logging.getLogger("fontTools").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def call_api(
    client: anthropic.Anthropic,
    prompt: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """single Anthropic API call. returns response text."""
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


# ---------------------------------------------------------------------------
# post-processing
# ---------------------------------------------------------------------------

def strip_header(text: str) -> str:
    """remove leading H1 header line to prevent condition fingerprinting."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip():
            if line.strip().startswith("# "):
                rest = lines[i + 1 :]
                while rest and not rest[0].strip():
                    rest.pop(0)
                return "\n".join(rest)
            break
    return text


def md_to_pdf(md_text: str, pdf_path: Path):
    """markdown → PDF via weasyprint."""
    html = md_lib.markdown(md_text, extensions=["tables", "fenced_code"])
    css = (
        "body { font-family: Georgia, serif; font-size: 11pt; "
        "line-height: 1.5; max-width: 7in; margin: 1in auto; } "
        "h1 { font-size: 16pt; margin-top: 0; } "
        "h2 { font-size: 14pt; } h3 { font-size: 12pt; } "
        "code { font-family: monospace; font-size: 10pt; "
        "background: #f5f5f5; padding: 2px 4px; } "
        "blockquote { border-left: 3px solid #ccc; margin-left: 0; "
        "padding-left: 1em; color: #555; }"
    )
    full = f"<html><head><style>{css}</style></head><body>{html}</body></html>"
    weasyprint.HTML(string=full).write_pdf(str(pdf_path))


# ---------------------------------------------------------------------------
# excavate batching
# ---------------------------------------------------------------------------

def batch_excavate_prompts(
    exp_dir: Path, subset_ids: list, batch_size: int = EXCAVATE_BATCH_SIZE
) -> list[str]:
    """build batched excavate prompts from individual prompt files.

    reads the shared skill definition once, then groups abstracts into
    batches of `batch_size` to reduce API calls.
    """
    excavate_dir = exp_dir / "condition_c" / "prompts" / "excavate"

    # extract skill definition from the first individual prompt
    first = (excavate_dir / f"{subset_ids[0]}.md").read_text()
    skill_def = first.split("\n---\n", 1)[0]

    # collect abstract sections
    abstracts = []
    for aid in subset_ids:
        text = (excavate_dir / f"{aid}.md").read_text()
        marker = f"## {aid}"
        idx = text.rfind(marker)
        abstract_section = text[idx:] if idx >= 0 else f"## {aid}\n[text not found]"
        abstracts.append(abstract_section)

    # create batched prompts
    batches = []
    for i in range(0, len(abstracts), batch_size):
        chunk = abstracts[i : i + batch_size]
        body = "\n\n".join(chunk)
        prompt = (
            f"{skill_def}\n\n---\n\n"
            "apply excavate (max_depth: 3) to each of the "
            "following conference abstracts. process them one at a time. "
            "for each abstract, output the full excavation: "
            "normalize the claim → layer-1 assumptions → layer-2 sub-assumptions "
            "→ crux map.\n\n"
            f"{body}"
        )
        batches.append(prompt)

    return batches


def condense_excavations_prompt(
    excavate_text: str, n_abstracts: int, conf: dict
) -> str:
    """prompt to synthesize raw excavations into cross-cutting patterns."""
    field = conf["domain"]["field"]
    abbrev = conf["conference"]["abbreviation"]
    year = conf["conference"]["year"]
    return (
        f"you have received excavations from {n_abstracts} "
        f"{field} conference abstracts ({abbrev} {year}). each reveals the "
        "implicit premises, structural assumptions, and fragilities beneath "
        "the research claims.\n\n"
        "synthesize these into cross-cutting patterns. organize by theme, "
        "not by individual abstract. focus on:\n"
        "1. shared assumption fragilities that recur across multiple papers\n"
        "2. common methodological blind spots\n"
        "3. implicit field-wide commitments no individual paper acknowledges\n"
        "4. tensions between papers holding incompatible assumptions\n\n"
        "be specific — cite abstract IDs. compress ruthlessly; this synthesis "
        "feeds a downstream reasoning stage.\n\n"
        f"## excavation outputs\n\n{excavate_text}"
    )


# ---------------------------------------------------------------------------
# condition runners
# ---------------------------------------------------------------------------

NO_HEADER_INSTRUCTION = (
    "\n\nIMPORTANT: Do not begin your response with a title or top-level "
    "header (no '# ...' first line). Start directly with your analytical "
    "content. Use ## and ### headers for internal structure only."
)


def run_condition_a(
    client: anthropic.Anthropic,
    exp_dir: Path,
    run_num: int,
    model: str = DEFAULT_MODEL,
    skip_pdf: bool = False,
) -> str:
    """execute condition A (naive prompt) for one run."""
    run_dir = exp_dir / "condition_a" / f"run_{run_num}"
    prompt = (run_dir / "prompt.md").read_text() + NO_HEADER_INSTRUCTION

    print(f"  [A/run_{run_num}] calling API ({model})...")
    t0 = time.time()
    response = strip_header(call_api(client, prompt, model))
    dt = time.time() - t0

    (run_dir / "response.md").write_text(response)
    if not skip_pdf:
        md_to_pdf(response, run_dir / "response.pdf")

    print(f"  [A/run_{run_num}] done ({dt:.0f}s, {len(response):,} chars)")
    return response


def run_condition_c(
    client: anthropic.Anthropic,
    exp_dir: Path,
    run_num: int,
    conf: dict,
    model: str = DEFAULT_MODEL,
    intermediate_model: str | None = None,
    skip_pdf: bool = False,
    max_workers: int = 6,
) -> str:
    """execute full condition C pipeline for one run.

    phases:
        1. [parallel] inductify + negspace + excavate batches
        2. condense excavations
        3. antithesize
        4. final synthesis
    """
    im = intermediate_model or model  # model for skill steps
    run_dir = exp_dir / "condition_c" / f"run_{run_num}"
    prompts_dir = exp_dir / "condition_c" / "prompts"
    config = json.loads((exp_dir / "config.json").read_text())
    subset_ids = config["subset_ids"]
    corpus_text = (exp_dir / "corpus_formatted.md").read_text()

    # ── phase 1: parallel skill calls ──────────────────────────────
    print(f"  [C/run_{run_num}] phase 1: inductify + negspace + excavate "
          f"({im})...")
    t0 = time.time()

    inductify_p = (prompts_dir / "step1a_inductify.md").read_text()
    negspace_p = (prompts_dir / "step1b_negspace.md").read_text()
    excavate_batches = batch_excavate_prompts(exp_dir, subset_ids)

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(call_api, client, inductify_p, im): "inductify",
            pool.submit(call_api, client, negspace_p, im): "negspace",
        }
        for i, bp in enumerate(excavate_batches):
            futures[pool.submit(call_api, client, bp, im)] = f"excavate_batch{i+1}"

        for fut in as_completed(futures):
            key = futures[fut]
            results[key] = fut.result()
            print(f"    [{key}] done")

    print(f"  [C/run_{run_num}] phase 1 complete ({time.time()-t0:.0f}s)")

    # save phase 1
    (run_dir / "step1a_inductify_response.md").write_text(results["inductify"])
    (run_dir / "step1b_negspace_response.md").write_text(results["negspace"])
    n_batches = len(excavate_batches)
    for i in range(n_batches):
        (run_dir / f"excavate_batch{i+1}.md").write_text(
            results[f"excavate_batch{i+1}"]
        )

    # ── phase 2: condense excavations ──────────────────────────────
    print(f"  [C/run_{run_num}] phase 2: condensing excavations...")
    all_excavate = "\n\n---\n\n".join(
        results[f"excavate_batch{i+1}"] for i in range(n_batches)
    )
    condense_p = condense_excavations_prompt(all_excavate, len(subset_ids), conf)
    condensed = call_api(client, condense_p, im)
    (run_dir / "excavate_condensed.md").write_text(condensed)
    print(f"    [condense] done")

    # ── phase 3: antithesize ───────────────────────────────────────
    print(f"  [C/run_{run_num}] phase 3: antithesize...")
    anti_p = antithesize_prompt(condensed, conf)
    anti_resp = call_api(client, anti_p, im)
    (run_dir / "step2_antithesize_response.md").write_text(anti_resp)
    print(f"    [antithesize] done")

    # ── phase 4: final synthesis ───────────────────────────────────
    print(f"  [C/run_{run_num}] phase 4: final synthesis ({model})...")
    skill_outputs = (
        f"### INDUCTIFY (structural patterns)\n\n{results['inductify']}\n\n"
        f"### NEGSPACE (conspicuous absences)\n\n{results['negspace']}\n\n"
        f"### EXCAVATE (assumption archaeology, {len(subset_ids)} abstracts "
        f"condensed)\n\n{condensed}\n\n"
        f"### ANTITHESIZE (constructive opposition)\n\n{anti_resp}"
    )
    synth_p = synthesize_with_skills_prompt(skill_outputs, corpus_text, conf)
    synth_p += NO_HEADER_INSTRUCTION

    final = strip_header(call_api(client, synth_p, model))

    (run_dir / "step3_synthesize_prompt.md").write_text(synth_p)
    (run_dir / "final_response.md").write_text(final)
    if not skip_pdf:
        md_to_pdf(final, run_dir / "final_response.pdf")

    print(f"  [C/run_{run_num}] done")
    return final


# ---------------------------------------------------------------------------
# judge prompt generation
# ---------------------------------------------------------------------------

def generate_judge_prompts(exp_dir: Path, run_num: int, conf: dict):
    """create judge evaluation prompts for both conditions of a run."""
    eval_dir = exp_dir / "evaluation"
    corpus_text = (exp_dir / "corpus_formatted.md").read_text()

    a_text = (exp_dir / "condition_a" / f"run_{run_num}" / "response.md").read_text()
    c_text = (exp_dir / "condition_c" / f"run_{run_num}" / "final_response.md").read_text()

    (eval_dir / f"judge_a_run{run_num}_prompt.md").write_text(
        judge_prompt(a_text, corpus_text, conf)
    )
    (eval_dir / f"judge_c_run{run_num}_prompt.md").write_text(
        judge_prompt(c_text, corpus_text, conf)
    )
    print(f"  [eval] judge prompts for run {run_num} saved")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Execute experiment runs via Anthropic API"
    )
    p.add_argument(
        "--experiment-dir", required=True, type=Path,
        help="experiment directory created by run.py",
    )
    p.add_argument(
        "--runs", nargs="+", type=int, required=True,
        help="which runs to execute (e.g. --runs 2 3)",
    )
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument(
        "--intermediate-model", default=None,
        help="cheaper model for skill steps (default: same as --model)",
    )
    p.add_argument(
        "--condition", choices=["a", "c", "both"], default="both",
        help="which condition(s) to run",
    )
    p.add_argument("--max-workers", type=int, default=6)
    p.add_argument("--skip-pdf", action="store_true")
    p.add_argument("--skip-judge", action="store_true")
    args = p.parse_args()

    exp_dir = Path(args.experiment_dir).resolve()
    if not exp_dir.exists():
        print(f"error: not found: {exp_dir}", file=sys.stderr)
        sys.exit(1)

    config = json.loads((exp_dir / "config.json").read_text())
    conf = load_conference(config["conference"])

    im = args.intermediate_model or args.model
    print(f"experiment:  {exp_dir.name}")
    print(f"conference:  {config['conference']}")
    print(f"model:       {args.model}")
    if im != args.model:
        print(f"intermediate:{im}")
    print(f"runs:        {args.runs}")
    print(f"condition:   {args.condition}")
    print()

    client = anthropic.Anthropic()

    for run_num in args.runs:
        print(f"{'='*50}")
        print(f"RUN {run_num}")
        print(f"{'='*50}")

        if args.condition in ("a", "both"):
            run_condition_a(
                client, exp_dir, run_num, args.model, args.skip_pdf
            )

        if args.condition in ("c", "both"):
            run_condition_c(
                client, exp_dir, run_num, conf,
                model=args.model,
                intermediate_model=args.intermediate_model,
                skip_pdf=args.skip_pdf,
                max_workers=args.max_workers,
            )

        if not args.skip_judge and args.condition == "both":
            generate_judge_prompts(exp_dir, run_num, conf)

        print()

    print("all runs complete.")


if __name__ == "__main__":
    main()
