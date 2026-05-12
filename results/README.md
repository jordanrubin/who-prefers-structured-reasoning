# Results

Aggregated evaluation outputs for the paper. The full raw generation outputs
(every Condition A / Condition C synthesis, every judge transcript) are not
redistributed here — available on request.

## `aggregate/`
- `judge_evals_full.md` — run-level AI-judge scores, all domains, both judge
  families (Claude Opus 4.6 and GPT-5 / Codex), six dimensions each.
- `judge_subscore_breakdown.md` — per-dimension deltas (C − A) by domain and
  judge family (the source for the paper's dimension tables).
- `iclr2025_judge_summary.md` — ICLR-specific judge summary.
- `pairwise_5seed.json`, `pairwise_comparison_5seed.md`,
  `pairwise_comparison_5seed_anon.md`, `pairwise_comparison_blinded.md` — the
  AAHS 5-seed pairwise text-comparison matrix (similarity, citation overlap,
  claim novelty, decision-artifact counts) and the anonymized/blinded views used
  for condition-classification.
- `iclr2025_blinded.json`, `iclr2025_blinded_comparison.md`,
  `iclr2025_blinding_key.md`, `blinding_key.json`, `blinding_key.md` — blinding
  keys and blinded comparison tables for the human-classification analyses.
- `falsifiability_and_fabrication.md` — the fabrication audits (claims in each
  output checked against the corpus) and falsifiability accounting.

## `ablation/`
The AAHS operation-ablation (drop one operation at a time, re-judge):
`ablation_scores.json` and `ablation_summary.md`. Per-leave-one-out judge
scores are under `per_run/aahs2026_20260208_100425/ablation/`.

## `per_run/`
One subdirectory per experiment run, named `<slug>_YYYYMMDD_HHMMSS`. Each
contains the run's `config.json` (model, seed, subset size, corpus size, the
deterministic excavate subset ids), `subset_ids.json`, and the structured
`judge_scores.json` files (`evaluation/judge_scores.json` for Opus;
`evaluation/codex_fresh_eval_*/judge_scores.json` for the GPT-5 replication;
`evaluation/subagent_judging_*/` / `evaluation/gpt_subagent_*/` for the
individual judge-instance runs). `analyze.py` consumes
`<run>/evaluation/judge_scores.json`.

Domains: `iclr2025_*` (machine learning, ICLR 2025 oral abstracts),
`aahs2026_*` (hand surgery, AAHS 2026 podiums + ePosters), `ausa2025_*`
(defense policy, AUSA 2025 news/policy articles).
