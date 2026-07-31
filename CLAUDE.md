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
- Tests: one file per stage, test_<stage>.py at the repo root, stdlib unittest, no
  pytest. Run `python3 -m unittest discover -p "test_*.py" -v`.
- Stages are plain functions called in sequence from one script, per SPEC.md
  Section 2, never framework components. Ingest (M1) is built; Validate, Sanitize,
  Dedup, Judge, and Guardrails follow.

## Current status
See PROGRESS.md