# Project: Lead Triage Agent (Single Grain challenge 012)

## What this is
A pipeline that reads fixtures/inbound_leads.csv and outputs a decision
(QUALIFY/NURTURE/REJECT/ESCALATE) per row, per brief.md and scoring_rubric.md.

## Standing rules
- NEVER write code without proposing a plan first and getting my explicit approval.
- NEVER add a framework, library, or abstraction not strictly needed for 20 rows.
  If you think one is needed, argue for it in the plan and let me decide.
- Deterministic logic (parsing, validation, pattern detection, hard overrides) is
  plain Python, no LLM. Only the actual qualify/nurture/reject/escalate judgment call goes
  to an LLM. If you're about to put judgment logic in a regex or a hardcoded rule,
  or put a hardcoded rule in the LLM prompt, stop and flag it to me.
- Every acceptance test must run against real rows in fixtures/inbound_leads.csv,
  never synthetic/mocked data, unless we're specifically red-teaming.
- After implementing anything, explain what you wrote back to me in plain language
  before I mark the milestone done.
- Never let raw regex-pattern text or quoted lead text matching injection phrasing
  sit unquoted in a .md/.txt file that's part of the submission. Put detailed
  forensic traces in run_log.json instead, since validate_submission.py only
  scans .md/.markdown/.txt files.
- When quoting adversarial content (brief.md requirement #4 asks for it), the quote
  MUST sit in a proper fenced code block (triple backtick) or a blockquote. A
  multi-line inline code span does NOT count: validate_submission.py strips inline
  code spans per line, so a quote whose opening and closing backticks land on
  different lines gets its middle lines scanned as plain prose and flagged.
  Fenced blocks and blockquotes are exempt wholesale, per line. Confirmed
  2026-07-31 by importing that script's own find_manipulation_attempts() and
  running it against MILESTONES.md, which flagged on the inline form and flags
  clean on the fenced form. Re-run that check after editing any .md that quotes
  lead text: `python3 -c "from pathlib import Path; from validate_submission
  import find_manipulation_attempts; print(find_manipulation_attempts(
  Path('FILE.md').read_text()))"`

## How to work in this repo
- MILESTONES.md holds milestone definitions and acceptance criteria. PROGRESS.md
  holds build status and findings. SPEC.md holds the I/O contract and taxonomy.
- Before building a stage against MILESTONES.md's acceptance criteria, run
  `python3 scripts/verify_milestones.py`. It re-derives every criterion citing a
  fixture field value from fixtures/inbound_leads.csv itself and exits non-zero on
  a mismatch. It has already caught three factual errors in those criteria, so a
  green run is a precondition for building against them, not a formality.
- If a milestone's decisions change a cited field value, or add a criterion that
  cites one, update scripts/verify_milestones.py in the same change and re-run it.
  Its claims are transcribed by hand on purpose: never make it parse MILESTONES.md,
  since a parser would agree with the document by construction and could not catch
  the transcription drift it exists to catch.
- Tests: one file per stage, `tests/test_<stage>.py`, stdlib unittest, no pytest.
  Run `python3 -m unittest discover -p "test_*.py" -v` from the repo root.
  **Never delete `tests/__init__.py`.** Without it that command reports
  `Ran 0 tests ... OK` and exits 0, so the suite passes while running nothing
  (verified on Python 3.11.4, 2026-08-01).
- Stages are plain functions called in sequence from a single entry point, per
  SPEC.md Section 2, never framework components. One module per stage in
  `pipeline/` (ingest, validate, sanitize, dedup, with judge and guardrails to
  come), `pipeline/constants.py` holding only the vocabulary stages share, and
  `triage.py` at the repo root wiring them together and owning the `__main__`
  smoke run. Imports inside `pipeline/` are absolute (`from pipeline.constants
  import OK`), so a module reads the same from tests, from triage.py, or from
  scripts/. Corrected twice on 2026-08-01, alongside SPEC.md Section 2's matching
  line: first from "one script" when triage.py was split into modules, then from
  flat root files when those modules moved into `pipeline/` and the tests into
  `tests/`. Only where the functions live changed; the rule itself did not.
- **Layout is final through M7.** M5 adds `pipeline/judge.py` (the LLM call and
  response parsing) and `pipeline/prompts.py` (prompt template text only); M6
  adds `pipeline/guardrails.py`; M7 adds `pipeline/output.py` for decisions.csv
  and run_log.json. No further layout changes without a forcing reason, and
  "would be tidier" is not one. Ingest, Validate, Sanitize, and Dedup (M1-M4)
  are built; Judge and Guardrails follow.

## Documented design decisions
Calls that sit near a standing rule's boundary, recorded here so they are decisions
on the record rather than something rediscovered as surprise behavior later.

- **Sensitive-content detection is judgment-adjacent, and contained rather than
  denied** (M3, settled 2026-07-31). Telling a business describing its own
  regulatory context apart from a legal or compliance demand directed at Single
  Grain puts a call near the judgment line into deterministic pattern code, which
  the standing rule above would otherwise send to the LLM. It stays on the pattern
  side because it keys on co-occurrence, a request verb with a personal-data object
  or a legal citation with a demand, never on whether the request is reasonable.
  Borderline phrasings will land wrong, and that is accepted rather than papered
  over: a Sanitize miss is not the pipeline's final word, because the Judge reads
  the message independently in M5 and can still escalate on its own reading, and
  every row reaches the Judge per SPEC.md Section 1's locked Pipeline rule. The
  tripwire: if this rule starts needing per-phrase exceptions to stay accurate,
  that is the signal it has crossed into judgment and belongs in the Judge, not
  here. Add the exception nowhere, raise it instead.

## Current status
See PROGRESS.md