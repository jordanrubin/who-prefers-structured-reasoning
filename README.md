# Who Prefers Structured Reasoning? AI Judges Do, Domain Experts Don't

Code, configs, prompts, and aggregated scores for the paper *"Who Prefers
Structured Reasoning? AI Judges Do, Domain Experts Don't"*
([`paper/who-prefers-structured-reasoning.pdf`](paper/who-prefers-structured-reasoning.pdf)).

**The finding.** We scaffold LLM corpus analysis with five cognitive operations
— pattern induction, absence detection, operational extraction, assumption
excavation, dialectical challenge — each formalized as a structured prompt, then
prepend their outputs to a single-shot synthesis prompt. Across three unrelated
domains (machine learning, hand surgery, defense policy; *n* = 758 documents)
the scaffolded pipeline reliably outperforms the bare single-shot baseline under
LLM-as-judge evaluation (+15.6% to +32.0%, replicated cross-model with GPT-5
judges) — yet three blinded domain experts could not reliably tell the two
apart, and the pipeline's strongest AI-judge dimension (assumption surfacing)
was uniformly perceived as stating field-obvious truths. The paper argues this
is a structural failure mode of rubric-based synthesis evaluation: AI judges
reward *structural explicitness*; practitioners value *epistemic novelty*.

This repository lets you **point the pipeline at any corpus and rerun it.**

---

## Repository layout

```
paper/                  the paper PDF + LaTeX source; the blinded human-eval synthesis PDF
prompts/operations/     the epistemic operation prompts
                        (vendored from the Future Tokens library — see prompts/README.md)
conferences/            one TOML per corpus (domain, audience, topic keywords); example.toml is the template
data/                   where corpus index.json files go — the corpora themselves are not redistributed; rebuild with the scrapers (data/README.md)
scripts/experiment/     the pipeline: corpus prep, prompt templating, orchestration, execution, evaluation, stats
scripts/scrapers/       reference scrapers that build the corpus index.json files for the three paper corpora (see scrapers/README.md for the schema)
scripts/run_ai_judge.py convenience runner for the 6-dimension AI judge
results/                aggregated judge scores, pairwise comparisons, fabrication audits, ablation
```

`requirements.txt` lists the Python dependencies. Python ≥ 3.11 is required
(`tomllib`). The PDF-rendering extras (`weasyprint`, `markdown`) are only needed
if you want `scripts.experiment.execute` to emit PDFs.

---

## The pipeline

Two conditions, one shared final prompt:

- **Condition A (baseline).** A single, domain-aware, audience-specific synthesis
  prompt given the full corpus. (`naive_prompt` in `scripts/experiment/prompts.py`.)
- **Condition C (pipeline).** Run the operations below, then prepend their outputs
  to the *identical* Condition A prompt. The only variable is whether the
  structured intermediates are in context.

```
corpus ──┬─ dimensionalize → score abstracts → quality weights ─┐
         ├─ inductify   (full corpus + weights) ────────────────┤
         ├─ negspace    (full corpus) ───────────────────────────┤
         ├─ handlize    (full corpus) ───────────────────────────┼─→ Condition A prompt ─→ Output C
         └─ excavate    (stratified random 30-doc subset, one call each)
                          └─ antithesize (on the excavations) ───┘
```

The operation prompts live in `prompts/operations/<op>/<OP>.md` (see
`prompts/README.md`). See `paper/who-prefers-structured-reasoning.pdf` Appendix A
for prose descriptions of each operation.

---

## Rerunning the pipeline on a new corpus

### 1. Build a corpus index

The pipeline consumes a single JSON file: an array of document objects. The
required schema (id, title, authors, affiliations, abstract_text, sections, url,
type) is documented in [`scripts/scrapers/README.md`](scripts/scrapers/README.md);
`scripts/scrapers/aahs2026.py` and `scripts/scrapers/iclr2025.py` are working
reference implementations you can adapt. Place the file at `data/<slug>_index.json`.

### 2. Write a conference config

Copy [`conferences/example.toml`](conferences/example.toml) to
`conferences/<slug>.toml` and fill in the conference metadata, the `field` and
`audience` strings (these template the synthesis prompt), the `index_path`, and
optional `topics` keyword buckets used for stratified sampling of the excavate
subset. `conferences/{iclr2025,aahs2026,ausa2025}.toml` are the paper's configs.

### 3. Generate the run

```bash
python -m scripts.experiment.run --conference <slug> [--seed 42] [--subset-size 30] [--runs 3]
```

This creates `data/experiments/<slug>_YYYYMMDD_HHMMSS/` containing
`corpus_formatted.md`, the deterministic excavate `subset_ids.json`,
`condition_a/run_*/prompt.md`, `condition_c/prompts/*.md` (one per operation
stage), and an `evaluation/` skeleton. No model calls happen here.

### 4. Execute the operations

Two interchangeable paths produce the same artifacts:

- **Anthropic API (automated).**
  ```bash
  export ANTHROPIC_API_KEY=...
  python -m scripts.experiment.execute --experiment-dir data/experiments/<slug>_... --runs 1 2 3
  ```
  Generates `condition_a/run_N/response.md` and `condition_c/run_N/final_response.md`
  plus all intermediate operation outputs and per-run judge prompts.

- **Agent-driven (how the paper was run).** The paper's runs were executed by
  Claude Code Task agents (Claude Opus 4.6), not the API. Open each generated
  `prompt.md` / `condition_c/prompts/*.md`, run it as a fresh agent with no
  knowledge of the other conditions, and save the response under the same
  `run_N/` paths the API path uses. `CLAUDE.md` has the step-by-step recipe.

### 5. Evaluate

- **AI judges** (6 dimensions, 1–5; the paper used 3 instances per condition):
  ```bash
  python scripts/run_ai_judge.py --experiment-dir data/experiments/<slug>_... --run 1 --n-evals 3
  ```
  For the cross-model replication, feed the `evaluation/judge_*_prompt.md` files
  to a different model family instead.
- **Human experts** (blinded, randomized, 5 gut-level dimensions):
  ```bash
  python -m scripts.experiment.evaluate data/experiments/<slug>_...
  ```
- **Statistics** (paired deltas, bootstrap CIs, Cohen's *d*):
  ```bash
  python -m scripts.experiment.analyze data/experiments/<slug>_...
  ```
- **Pairwise text comparison** (similarity, citation overlap, claim novelty,
  decision-artifact counts) — used for the blinded condition-classification
  analyses:
  ```bash
  python -m scripts.experiment.compare data/experiments/<slug>_...
  ```

---

## Reproducing the paper's numbers

The three paper corpora are **not redistributed** here — rebuild them with
`scripts/scrapers/` (see `data/README.md`) into `data/<slug>_index.json`. The
configs are `conferences/{iclr2025,aahs2026,ausa2025}.toml` — *n* = 213, 218,
327 respectively, matching the paper.

This public repo includes the **aggregated scores only** — see `results/`:
`judge_evals_full.md` and `judge_subscore_breakdown.md` (Opus + GPT-5 judge
scores, run-level), `iclr2025_judge_summary.md`, the `pairwise_*` comparison
matrices and keys, `falsifiability_and_fabrication.md` (the fabrication audits),
`ablation/` (the AAHS operation-ablation), and `per_run/` (each run's
`config.json`, `subset_ids.json`, and the structured judge `judge_scores.json`).
The full raw generation outputs (every Condition A/C synthesis, every judge
transcript) are not redistributed here; they are available on request.

Runs are deterministic given a fixed seed (subset sampling, bootstrap, blinding
order); hosted-model nondeterminism introduces residual variation.

---

## The vendored operation prompts

`prompts/operations/` contains the epistemic-operation prompts used by the
pipeline, vendored from the **Future Tokens** reasoning-operations library by
Jordan Rubin, licensed CC BY 4.0. See `prompts/README.md` and
`prompts/operations/LICENSE`. The pipeline reads them via
`scripts/experiment/prompts.py`; to swap in a revised prompt, replace
`prompts/operations/<op>/<OP>.md`.

---

## Citation

If you use this repository, please cite the paper (see `CITATION.cff`).

## License

Code in this repository: MIT (see `LICENSE`). The operation prompts under
`prompts/operations/`: CC BY 4.0 (Jordan Rubin / Future Tokens). The
experimental corpora are not redistributed here — rebuild them with the scrapers
(`data/README.md`); copyright in those abstracts and articles belongs to their
original authors and publishers.
