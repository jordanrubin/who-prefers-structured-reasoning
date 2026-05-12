"""prompt templates for both experimental conditions.

condition A (baseline) uses naive_prompt().
condition C (pipeline) uses the same naive_prompt() but with the structured
operation outputs prepended as context.

the epistemic operations (inductify, negspace, handlize, excavate, antithesize,
dimensionalize, synthesize) are prompts vendored from the Future Tokens library
under prompts/operations/ -- see prompts/README.md. one file per operation,
UPPERCASE, named {OPERATION}.md (e.g. EXCAVATE.md).

all prompts are templated from a conference config dict (see config.py).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OPERATIONS_PATH = REPO_ROOT / "prompts" / "operations"


def _load_operation(name: str) -> str:
    """load an epistemic operation prompt (files are UPPERCASE: {NAME}.md)."""
    path = OPERATIONS_PATH / name / f"{name.upper()}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"operation prompt not found: {path}\n"
            f"expected a vendored Future Tokens prompt under prompts/operations/."
        )
    return path.read_text(encoding="utf-8")


def _conf_header(conf: dict) -> str:
    """one-line conference descriptor, e.g. 'AAHS 2026 Annual Meeting'."""
    c = conf["conference"]
    return f"{c['abbreviation']} {c['year']} {c['event']}"


def _types_str(conf: dict) -> str:
    """e.g. '82 podium presentations and 136 ePosters'."""
    counts = conf["_type_counts"]
    parts = []
    for t, n in sorted(counts.items(), key=lambda x: -x[1]):
        label = t + "s" if not t.endswith("s") else t
        # prettify: "podium" -> "podium presentations", "eposter" -> "ePosters"
        if t == "podium":
            label = "podium presentations"
        elif t == "eposter":
            label = "ePosters"
        parts.append(f"{n} {label}")
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# the shared final prompt (used by BOTH conditions)
# ---------------------------------------------------------------------------

def naive_prompt(corpus_text: str, conf: dict) -> str:
    c = conf["conference"]
    d = conf["domain"]
    total = conf["_corpus_size"]
    types = _types_str(conf)

    focus = d.get('synthesis_focus', '')
    focus_block = ""
    if focus:
        focus_block = f"""
Focus on {focus}. \
Deprioritize purely descriptive summaries in favor of analytical claims \
that would change what your reader does next.\n
"""

    return f"""\
You are analyzing the complete set of {total} abstracts from the {c['name']} \
({c['abbreviation']}) {c['year']} {c['event']} ({c['dates']}, {c['location']}). \
These include {types} spanning the full range \
of {d['field']} research.

Your audience is {d.get('audience', 'a specialist researcher')} who wants to \
understand what this collection reveals about the current state and trajectory \
of the field. They want more than a summary — they want insight.

{focus_block}\
What does this corpus tell us? What patterns emerge across these {total} studies? \
Where is the field concentrating its energy, and what areas appear \
underrepresented? \
Be specific. Reference abstract IDs when making claims. If something is \
noteworthy — because of its novelty, its implications, or the size of the \
effect — highlight it.

Here are all {total} abstracts:

{corpus_text}"""


# ---------------------------------------------------------------------------
# condition C: skill prompts
# ---------------------------------------------------------------------------

def dimensionalize_prompt(conf: dict) -> str:
    """generate quality dimensions for scoring individual abstracts."""
    skill = _load_operation("dimensionalize")
    header = _conf_header(conf)
    field = conf["domain"]["field"]
    return f"""{skill}

---

dimensionalize the concept of "quality of a {field} conference abstract."

these are 300-400 word research abstracts from {header}. we need 4-6 \
dimensions that distinguish high-quality abstracts from weak ones, suitable \
for weighting abstracts in a downstream corpus synthesis.

the dimensions should be scorable from the abstract text alone (no full paper needed). \
output the dimensions with clear 1-5 scoring criteria for each."""


def score_abstracts_prompt(dimensions_text: str, corpus_text: str, conf: dict) -> str:
    """score each abstract on the quality dimensions."""
    total = conf["_corpus_size"]
    field = conf["domain"]["field"]
    return f"""\
you have been given quality dimensions for {field} conference abstracts. \
score each of the following {total} abstracts on each dimension (1-5 scale). \
output as a JSON array of objects: [{{"id": "HS1", "scores": {{"dim1": 3, ...}}, "composite": 3.5}}, ...]

## quality dimensions

{dimensions_text}

## abstracts

{corpus_text}"""


def handlize_prompt(corpus_text: str, conf: dict) -> str:
    """extract operational handles from each abstract."""
    skill = _load_operation("handlize")
    total = conf["_corpus_size"]
    field = conf["domain"]["field"]

    instruction = f"""\
handlize each of the following {total} {field} conference abstracts. \
for each one, extract the operational handles — the claims, findings, methods, \
or conclusions with actual grip. strip rhetorical mass and boilerplate. \
keep only what a researcher or practitioner could act on, cite, or build from."""

    return f"""{skill}

---

{instruction}

output format for each:
## [ID]: [title]
- handle 1
- handle 2
- ...

{corpus_text}"""


def inductify_prompt(corpus_text: str, conf: dict, weights_text: str = "") -> str:
    """identify structural patterns across the corpus."""
    skill = _load_operation("inductify")
    total = conf["_corpus_size"]
    header = _conf_header(conf)
    field = conf["domain"]["field"]
    weight_section = ""
    if weights_text:
        weight_section = f"""
## abstract quality scores (for weighting)

{weights_text}

use these scores to weight your pattern extraction — patterns supported by \
higher-quality abstracts should be given more confidence.

"""

    return f"""{skill}

---

inductify across the following collection of {total} {field} conference \
abstracts from {header}. these are your examples.

what non-obvious commonalities, shared constraints, or latent mechanisms \
run across this corpus? what patterns would a {field} researcher NOT notice \
from reading abstracts individually?

{weight_section}## corpus

{corpus_text}"""


def negspace_prompt(corpus_text: str, conf: dict) -> str:
    """detect what's absent or structurally implied in the corpus."""
    skill = _load_operation("negspace")
    total = conf["_corpus_size"]
    header = _conf_header(conf)
    field = conf["domain"]["field"]

    instruction = f"""\
apply this to the following corpus of {total} {field} conference abstracts \
from {header}.

what SHOULD be present given the statistical structure of this corpus but is \
conspicuously absent? what conclusions aren't being drawn? what premises \
aren't being examined? what topics, methods, or populations are missing \
from a field that claims to cover {field}?"""

    return f"""{skill}

---

{instruction}

## corpus

{corpus_text}"""


def excavate_prompt(abstract_text: str, abstract_id: str, conf: dict) -> str:
    """excavate assumptions beneath a single abstract."""
    skill = _load_operation("excavate")
    field = conf["domain"]["field"]

    instruction = f"""\
apply this to the following {field} conference abstract.

max_depth: 3"""

    return f"""{skill}

---

{instruction}

## {abstract_id}

{abstract_text}"""


def antithesize_prompt(excavate_outputs: str, conf: dict) -> str:
    """generate the strongest opposing perspective from the excavated assumptions."""
    field = conf["domain"]["field"]
    skill = _load_operation("antithesize")

    return f"""{skill}

---

you have received excavations from 30 {field} conference abstracts. \
these reveal the implicit premises and structural assumptions beneath the \
research claims.

apply this to the excavation results below. purpose: robustify.

the output should be comprehensible on its own — a complete alternative \
perspective on what {field} research should be examining.

## excavation results

{excavate_outputs}"""


def synthesize_with_skills_prompt(
    skill_outputs: str,
    corpus_text: str,
    conf: dict,
) -> str:
    """the final prompt for condition C: same naive prompt but with skill outputs in context."""
    return f"""\
## prior structured analysis

the following analyses were performed on this corpus using specialized \
reasoning tools. use them as additional context — they represent different \
analytical lenses applied to the same material. do not mention the names of \
these tools or analytical stages in your synthesis.

{skill_outputs}

---

## your task

{naive_prompt(corpus_text, conf)}"""


# ---------------------------------------------------------------------------
# evaluation prompts
# ---------------------------------------------------------------------------

def _judge_rubric(conf: dict) -> str:
    total = conf["_corpus_size"]
    header = _conf_header(conf)
    field = conf["domain"]["field"]
    return f"""\
you are evaluating a synthesis of {total} {field} conference abstracts \
from {header}. score the following output on 6 dimensions (1-5 scale). \
score strictly — 3 means competent but unremarkable, 5 is genuinely impressive.

## dimensions

1. CROSS-ABSTRACT INFERENCE DENSITY (1-5)
   what % of claims require information from ≥2 abstracts?
   1 = restates individual abstracts; 5 = nearly every claim synthesizes across papers

2. EPISTEMIC STRATIFICATION (1-5)
   does the output distinguish between what the corpus SHOWS (evidence), \
SUGGESTS (inference), and is MISSING (gaps)?
   1 = flat, all claims at same confidence; 5 = explicit layering throughout

3. FALSIFIABILITY YIELD (1-5)
   how many specific, testable predictions or hypotheses does it generate?
   1 = pure description; 5 = multiple concrete hypotheses with breaking conditions

4. CORPUS COVERAGE EFFICIENCY (1-5)
   are the major topic clusters proportionally represented?
   1 = fixates on 1-2 topics; 5 = integrates across the full breadth

5. ASSUMPTION SURFACING RATE (1-5)
   does it make explicit any implicit field-wide assumptions not stated \
in individual abstracts?
   1 = takes corpus at face value; 5 = identifies multiple shared blind spots

6. DECISION-READINESS (1-5)
   could a {field} specialist use this to change behavior or prioritize research?
   1 = purely descriptive; 5 = specific actionable recommendations with conditions

for each dimension provide:
- score (integer 1-5)
- 1-2 sentence justification with specific examples from the output

also provide a list of any claims in the output that appear fabricated \
or not supportable from the corpus.

## the corpus (for verification)

{{corpus}}

## the output being evaluated

{{output}}"""


def judge_prompt(output_text: str, corpus_text: str, conf: dict) -> str:
    rubric = _judge_rubric(conf)
    return rubric.format(output=output_text, corpus=corpus_text)


def human_scoring_instructions(conf: dict) -> str:
    field = conf["domain"]["field"]
    return f"""
score this synthesis on 5 dimensions (1-5 scale).
you have NOT read the underlying abstracts — score on face value.

1. "I DIDN'T KNOW THAT" — did it tell you something you didn't already
   know or assume about {field} research? (1=nothing new, 5=genuinely surprised)

2. "I'D FORWARD THIS" — would you send this to a colleague, fellow, or
   use it to frame a research meeting? (1=no, 5=immediately)

3. "THIS IS SPECIFIC" — are claims concrete enough to act on, or could you
   swap "{field}" for any field? (1=generic, 5=unmistakably this field)

4. "THIS IS HONEST" — does it feel calibrated? or does it oversell, hedge
   too much, or trigger your bullshit detector? (1=suspicious, 5=trustworthy)

5. "I'D CHANGE SOMETHING" — is there a concrete thing you'd do differently
   after reading this? (1=no, 5=yes and I can name it)
"""
