# Running the pipeline (agent recipe)

This repo is designed to be driven by an agent (e.g. Claude Code). Read
`README.md` first for the full picture. This file is the operational checklist
for *executing a pipeline run* on a corpus.

## Inputs you need from the user
- A corpus, either already in `data/<slug>_index.json` form or as raw material
  you can scrape into that form (schema: `scripts/scrapers/README.md`).
- A `conferences/<slug>.toml` (copy `conferences/example.toml`): conference
  metadata, `domain.field`, `domain.audience`, optional `domain.synthesis_focus`,
  optional `topics` keyword buckets.

## Steps
1. **Prep.** `python -m scripts.experiment.run --conference <slug>`
   → creates `data/experiments/<slug>_YYYYMMDD_HHMMSS/` with `corpus_formatted.md`,
   `subset_ids.json`, `condition_a/run_*/prompt.md`, `condition_c/prompts/*.md`.
   No model calls. Note the experiment dir path.

2. **Condition A (baseline).** For each run `N`: execute
   `condition_a/run_N/prompt.md` as a *fresh* agent with no knowledge of
   Condition C or that any intervention exists. Save the reply to
   `condition_a/run_N/response.md`.

3. **Condition C (pipeline).** For each run `N`:
   - Run, in parallel, `condition_c/prompts/step0a_dimensionalize.md`,
     `step0b_handlize.md`, `step1a_inductify.md`, `step1b_negspace.md`, and the
     per-document `condition_c/prompts/excavate/*.md` (one agent each). Save each
     reply alongside as `*_response.md` / under `run_N/`.
   - Score the corpus with the dimensionalize output, feed weights into the
     inductify step (the generated prompts already wire this).
   - Run `step2_antithesize` on the concatenated excavate outputs → save.
   - Assemble `step3_final` = the Condition A prompt with all operation outputs
     prepended (the `step3_final_TEMPLATE.md` shows the assembly), run it → save
     `condition_c/run_N/final_response.md`.
   - `scripts.experiment.execute` automates all of this against the Anthropic
     API if an `ANTHROPIC_API_KEY` is available — prefer it when you can.

4. **AI judge.** `python scripts/run_ai_judge.py --experiment-dir <dir> --run N --n-evals 3`
   (needs `ANTHROPIC_API_KEY`), or feed `evaluation/judge_*_prompt.md` to judge
   agents yourself and write the scores into `evaluation/judge_scores.json` in
   the documented flat format (`condition`, `run`, `eval`, six dimension ints,
   `composite`).

5. **Analyze.** `python -m scripts.experiment.analyze <dir>` for paired deltas,
   bootstrap CIs, Cohen's *d*. `python -m scripts.experiment.compare <dir>` for
   the pairwise text-similarity / claim-novelty comparison.

6. **(Optional) Human eval.** `python -m scripts.experiment.evaluate <dir>` —
   interactive, blinded, randomized; for a reviewer who has *not* read the corpus.

## Invariants to preserve
- The Condition A prompt and the final Condition C prompt are byte-identical
  except for the prepended operation outputs. Do not "improve" one and not the
  other.
- Condition A agents must not see Condition C, the operation prompts, or the
  word "pipeline". Judges must not know which output came from which condition.
- The excavate subset is deterministic from `--seed`; don't resample per run.
