# Epistemic operation prompts

`prompts/operations/` holds the structured prompts the pipeline uses for its
epistemic operations. They are vendored, unmodified, from the **Future Tokens**
reasoning-operations library by Jordan Rubin (CC BY 4.0 — see `operations/LICENSE`
and `operations/TRADEMARK.md`).

One file per operation, uppercase, named `{OPERATION}.md`:

```
operations/
  inductify/      INDUCTIFY.md      pattern induction: non-obvious commonalities across the corpus
  negspace/       NEGSPACE.md       absence detection: what should be present but is conspicuously missing
  handlize/       HANDLIZE.md       operational extraction: claims/findings/methods with actual grip
  excavate/       EXCAVATE.md       assumption excavation: implicit premises beneath a document's conclusions
  antithesize/    ANTITHESIZE.md    dialectical challenge: the strongest opposing perspective
  dimensionalize/ DIMENSIONALIZE.md (supporting) quality dimensions used to weight documents for inductify
```

`scripts/experiment/prompts.py` loads these via `OPERATIONS_PATH = prompts/operations/`,
templating each one with the corpus (or a single document) and the conference
config. See `paper/who-prefers-structured-reasoning.pdf` Appendix A for prose
descriptions of what each operation does.

To swap in a revised operation prompt, replace `operations/<operation>/<OPERATION>.md`.
The fuller Future Tokens / runeforge libraries (and other operations not used by
this pipeline) live upstream; this repo vendors only what the pipeline invokes.
