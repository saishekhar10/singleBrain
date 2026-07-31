# PROGRESS.md

Build status for the Lead Triage Agent. Milestone definitions live in
MILESTONES.md; this file records what is actually built, what running it
produced, and what that turned up. Numbers are labeled per brief.md
requirement #4.

| Milestone | Status |
|---|---|
| M1 Ingest | Implemented, tests green, awaiting sign-off |
| M2 Validate | Not started (two parsing decisions still need sign-off; acceptance criteria corrected, see below) |
| M3 Sanitize | Not started (one sensitive-content decision needs sign-off; L-020 criteria widened, see below) |
| M4 Dedup | Not started (acceptance criteria corrected, see below) |
| M5 Judge | Not started |
| M6 Guardrails | Not started |
| M7 Full run | Not started |
| M8 Manual comparison | Not started |
| M9 Red-team pass | Not started |
| M10 Validator loop | Not started |

---

## M1: Ingest

**Files:** `triage.py` (`SCHEMA`, `ingest()`, a `__main__` smoke run),
`test_ingest.py` (7 tests, stdlib `unittest`).

**Run it:**

```
python3 triage.py                      # defaults to fixtures/inbound_leads.csv
python3 triage.py <path-to-csv>
python3 -m unittest test_ingest -v
```

**What it does:** reads the CSV into a list of dicts of raw strings, in file
order, and nothing else. No row is dropped, reordered, or mutated. No value is
stripped, coerced, or unescaped. The only error it raises is a header that does
not match `SCHEMA`, which is a file-contract violation rather than a row-level
problem.

**Observed results** [observed, 2026-07-31, Python 3.11.4]:

- 20 data rows ingested, fixture is 21 physical lines.
- All of L-001 through L-020 present, in file order.
- 7 of 7 tests pass.

**Blank cells, measured rather than assumed** [observed]:

- `email` blank: L-004 only.
- `company` blank: L-002, L-008, L-015, L-019.
- `website` blank: L-002, L-008, L-010, L-013, L-015, L-019.
- `message` blank: L-018.

**Known untested path:** `ingest()`'s header-mismatch `ValueError`. Covering it
requires a CSV with a wrong header, which is synthetic data, so per CLAUDE.md it
is left untested at M1 rather than tested against a fabricated file.

---

## Finding: L-008 was misfiled as a blank-email row

Kept in the record because of how it surfaced, not just what it was.

**How it surfaced.** M1's tests were written before `ingest()` existed, with the
blank-field expectations transcribed from MILESTONES.md's M2 criteria. The first
green-phase run went red on one assertion: MILESTONES.md said `email` was blank
on L-004 and L-008, and the fixture disagreed. The test was wrong, not the code.
Nothing about M1's own goal (read 20 rows, mutate nothing) would have caught
this; it surfaced only because the acceptance criteria were encoded as
executable assertions against the real file before any code existed to satisfy
them.

**What was actually wrong.** L-004 is the only blank-`email` row in the fixture
[observed]. L-008 carries a real personal-provider address,
`rickalvarez88@gmail.com`, with blank `company` and blank `website`.

**Why it mattered beyond a typo.** The two route differently and would have
produced different pipeline behavior if built as written:

- A blank `email` forces `identity_verifiability` to 0.0 through SPEC.md
  Section 6's email clause.
- L-008 instead reaches that same 0.0 through the blank-`company` clause, and
  its personal-provider domain is a signal SPEC.md Section 5's design note says
  to compute deterministically and hand to the Judge to weigh, not a missing
  field at all. L-008 is Section 5 criterion 1's unverifiable-identity path.
- In M4, treating L-008 as blank would have excluded a real, matchable email
  from dedup entirely.

**Fixes applied to MILESTONES.md** [observed, 2026-07-31]: M2's `email` bullet
and M4's blank-email bullet both rewritten; M4's "16 distinct, non-blank
emails" corrected to 17 (see the verification pass below, where that third
instance was caught).

---

## Verification pass: M2-M6 acceptance criteria against the raw fixture

Run because the L-008 error proved the drift happened while translating the
objective-facts table into MILESTONES.md's wording, which means the table is not
a safe thing to re-check against. Every M2-M6 acceptance criterion citing a
specific lead_id's field value was re-derived from
`fixtures/inbound_leads.csv` directly.

**Method:** `scripts/verify_milestones.py`, in the repo as re-runnable
evidence rather than a description of having checked once. It encodes each
cited claim as an assertion against `ingest()`'s output and exits non-zero on
any discrepancy, so it works as a gate and not just a report. Claims are
transcribed into the script by hand on purpose: a version that parsed
MILESTONES.md would agree with the document by construction, which is the exact
failure it exists to catch. Reusable for M8's comparison and M10's loop.

**Result [observed, 2026-07-31]:** the first run was 38 of 40 claims verified
with 3 factual errors found. After the corrections below, `python3
scripts/verify_milestones.py` reports **41 of 41 verified, 0 discrepancies, 1
note, exit 0**.

**Correction 3, applied.** M4 claimed 16 distinct non-blank emails. The fixture
has 19 non-blank email rows carrying 17 distinct values [observed], the two
duplicate pairs accounting for 4 rows sharing 2 values. The old figure of 16 is
exactly what you get by assuming L-008 is blank, so this was the same error
propagating a second hop rather than an independent mistake. Corrected in place,
with the derivation written into the bullet so the number can be re-checked
without recomputing it.

**Note 1, no change made.** M3's citation for L-019 is an accurate substring of
that row's `message`, but not the whole field: the actual message is 115
characters and continues past the quoted sentence [observed].

**Note 2, resolved: M3's L-020 criteria widened to the full message.** The old
citation omitted the message's opening sentence, which manufactures a prior
business relationship before the payment demand appears, so a detector could
have satisfied the criterion while keying only on urgency-plus-executable-link.
M3 now names two patterns for that row: (a) false-prior-relationship pretext,
(b) urgency framing plus a link to an executable. Three additions came with it:

- **V3**, a synthetic security-threat variant carrying pattern (a) and a
  payment demand with no URL, no attachment, and no file extension anywhere. A
  detector that needs a link to fire fails it.
- **N2**, a false-positive check holding a legitimate returning customer who
  references a real prior conversation with no demand, urgency, payment
  request, or link. This is the necessary guard: without it, widening toward
  pattern (a) produces a detector that flags every returning customer.
- A **judgment-vs-pattern flag** written into M3 per CLAUDE.md. Whether a
  claimed prior relationship is false is not determinable from the row, since a
  real returning customer writes the same sentence truthfully. Sanitize must
  key on the co-occurrence of an unverifiable relationship claim with a
  payment/credential demand, urgency, or an actionable link, never on
  prior-relationship phrasing by itself.

**Separate finding, fixed: MILESTONES.md tripped the submission linter.**
Scanning the repo's own `.md` files with `find_manipulation_attempts()`
imported directly from `validate_submission.py` flagged MILESTONES.md line 148
[observed]. Cause: M3 quoted L-006's triggering text in an inline code span
whose backticks opened and closed on different lines, and the linter strips
inline code spans per line, so the middle of the quote was scanned as ordinary
prose. Fenced blocks are exempt wholesale, so the three real-fixture citations
in M3 were moved into one `text` fence. Re-scanned after the change:
MILESTONES.md, PROGRESS.md, SPEC.md, and CLAUDE.md all flag clean [observed].
Now codified as a standing rule in CLAUDE.md, with the one-liner for re-running
that check against any edited `.md`. It matters most for the write-up itself,
where brief.md requirement #4 explicitly asks for adversarial content to be
quoted: fenced or blockquoted is fine, a multi-line inline span is neither.
All of MILESTONES.md's quoted lead text and synthetic variants were moved into
fences as part of this. Repo `.md` scan after the change: BEAT_CLAUDE_README,
CLAUDE, MILESTONES, PROGRESS, SPEC, brief, and scoring_rubric all flag clean
[observed]. SCORING.md flags twice, but it is the challenge's own provided file
describing the check and is not part of our submission packet.

**Everything else verified clean**, including all four M2 blank-field lists, all
four M2 budget values, L-012's invalid `submitted_at`, L-010's and L-016's
malformed-scope cells, both M4 duplicate pairs, M3's four false-positive rows,
and M6's three arithmetic checks (0.825 weighted average, 0.6 data completeness,
the 0.2 trust-risk cap binding).
