# PROGRESS.md

Build status for the Lead Triage Agent. Milestone definitions live in
MILESTONES.md; this file records what is actually built, what running it
produced, and what that turned up. Numbers are labeled per brief.md
requirement #4.

| Milestone | Status |
|---|---|
| M1 Ingest | **Done**, signed off 2026-07-31 (7/7 tests green) |
| M2 Validate | **Done**, signed off 2026-07-31 (33/33 tests green; all parsing and signal decisions signed off same day) |
| M3 Sanitize | **Done**, signed off 2026-07-31 (37/37 tests green; all four decisions signed off same day) |
| M4 Dedup | **Built**, 33/33 tests green, awaiting sign-off (five rules signed off 2026-08-01) |
| M5 Judge | Not started |
| M6 Guardrails | Not started |
| M7 Full run | Not started |
| M8 Manual comparison | Not started |
| M9 Red-team pass | Not started |
| M10 Validator loop | Not started |

---

## Structural refactor: one module per stage, 2026-08-01

Pure reorganization before M5 starts, no behavior change and no new logic.
`triage.py` was 804 lines carrying M1 to M4; it is now a 64-line entry point
that imports four stage modules and wires them in sequence.

| File | Lines | Holds |
|---|---|---|
| `pipeline/ingest.py` | 48 | `SCHEMA`, `EXTRA_FIELDS_KEY`, `ingest()` |
| `pipeline/constants.py` | 29 | the four status words, the three category names, `CONTENT_CATEGORIES` |
| `pipeline/validate.py` | 330 | M2, plus `DOMAIN_SIGNALS` |
| `pipeline/sanitize.py` | 274 | M3 |
| `pipeline/dedup.py` | 108 | M4 |
| `triage.py` | 64 | imports, `DEFAULT_FIXTURE`, the `__main__` smoke run |

No import cycles: `validate` imports `ingest`, everything imports `constants`,
`triage` imports the four stages. `python3 triage.py fixtures/inbound_leads.csv`
is unchanged, and so is the `__main__` block's body. The modules landed at the
repo root first and moved into `pipeline/` later the same day; see the folder
move below.

**Why `constants.py` exists at all**, since a file of seven strings needs a
reason under the no-unnecessary-abstraction rule: SPEC.md Section 6 has M6
reading Validate's field statuses and Sanitize's content categories back off
their output. Without a shared home, Guardrails would import from Validate's or
Sanitize's module to borrow a string, coupling stages that are meant to be
independent. `CONTENT_CATEGORIES` lives there for the same reason, since M6's
`trust_risk` priority reads exactly those three names. No logic is in that file.

**Baseline recorded before the split, and matched after** [observed,
2026-08-01, Python 3.11.4]. The bar was identical output, not a passing run:

| | Before | After |
|---|---|---|
| `unittest discover -v` | 110 tests, 110 `ok`, exit 0 | 110 tests, 110 `ok`, exit 0 |
| `scripts/verify_milestones.py` | 55/55, 0 discrepancies, 1 note, exit 0 | 55/55, 0 discrepancies, 1 note, exit 0 |
| `python3 triage.py fixtures/...` | 20 rows, exit 0 | 20 rows, exit 0 |

Verified by `diff` on the full verbose output of all three runs, not by
comparing totals: every individual test name and every individual claim line
matches, ignoring only unittest's timing line.

**Code-move integrity checked independently of the tests.** Comparing the
pre-split file against the six new ones as line multisets, ignoring module
docstrings, imports, and the `# ---- M2/M3/M4` dividers: 568 code lines before,
568 after, with exactly one line differing, a comment on `DOMAIN_SIGNALS` whose
"the smoke run below" stopped being true when it moved to `validate.py`
[observed]. No code line was added, dropped, or altered.

**The one way this refactor could have passed its own acceptance bar while
regressing.** `AntiOverfitTest.compiled_patterns()` scanned `vars(triage)`,
which before the split held all 27 compiled patterns, including Validate's
`_EMAIL_SHAPE`, `_URL_SCHEME`, and `_BUDGET_SHAPE`. Repointing it at
`sanitize.py` alone would have left the suite at 110 green tests while silently
dropping Validate's three from anti-overfit coverage. It now scans all four
stage modules from an explicit `STAGE_MODULES` list, and the pattern *set*, not
just the count, was compared before and after: 27 both times, identical names,
none missing [observed]. The existing "more than 5" floor stays as the
assertion; 27 is deliberately not pinned, since M5 and M6 will add real patterns
and a fixed number would just need upkeep.

**Two signed-off documentation lines corrected, not silently edited.** SPEC.md
Section 2's Non-Goals bullet and CLAUDE.md's matching rule both read "plain
functions called in sequence from one script", which stopped being true here.
Both now say "from a single entry point" and carry a dated note saying what
changed and why. The Non-Goal itself is unchanged: still plain functions, still
no framework, no orchestration library, nothing passing messages between
components. CLAUDE.md's cross-reference to SPEC.md Section 2 was checked at the
same time and was already correct, so it was left alone.

---

## Folder move: `pipeline/` and `tests/`, 2026-08-01

Second reorganization the same day, and the last one: the five stage modules
moved from the repo root into `pipeline/`, the four test files into `tests/`,
and `triage.py` stayed at the root as the entry point. Same acceptance bar as
the module split, same result.

**Layout is now final through M7**, recorded in CLAUDE.md as a rule rather than
an intention. M5 adds `pipeline/judge.py` and `pipeline/prompts.py`, M6 adds
`pipeline/guardrails.py`, M7 adds `pipeline/output.py`. No further layout
changes without a forcing reason; "would be tidier" does not count. Two
reshuffles in one day is already the cost this rule exists to stop paying,
and SPEC.md Section 2's Non-Goals line has now been corrected twice within it.

**Where M5's prompt text will live, decided now so the layout question is
closed before the milestone starts:** `pipeline/prompts.py`, holding the
template text and the assembly that wraps lead content in its labeled data
boundary, with `pipeline/judge.py` holding the call and the response parsing.
Split rather than inlined for a specific reason: M5's acceptance criteria
require the rubric to be checked *by reading the prompt text* (all three
QUALIFY criteria, all six ESCALATE triggers, the REJECT test, both NURTURE
sub-cases, the duplicate rule), and a test that reads one small module is a
different thing from one that greps a long string embedded in call logic. It
also keeps CLAUDE.md's rule against hardcoded logic in the prompt auditable in
one place. The constraint that comes with it: `prompts.py` holds template text
and boundary assembly only, never a decision rule, or it has become the
judgment-in-hardcoded-logic problem in a new location.

**`tests/__init__.py` is load-bearing, not boilerplate** [observed, Python
3.11.4, 2026-08-01]. Without it, the documented `python3 -m unittest discover
-p "test_*.py" -v` reports `Ran 0 tests in 0.000s`, `OK`, exit 0. The suite
would pass while running nothing, which is indistinguishable from success at a
glance and would have hidden every regression this repo tests for. `-s tests
-t .` does not work around it either: `ImportError: Start directory is not
importable`. Checked before the move rather than discovered after, and the
reason is written into the file's own docstring and into CLAUDE.md, since the
failure mode is silent and the fix is a file that looks deletable.

**Acceptance bar, matched** [observed, 2026-08-01]:

| | Baseline (pre-split) | After folder move |
|---|---|---|
| `unittest discover -v` | 110 tests, 110 `ok`, exit 0 | 110 tests, 110 `ok`, exit 0 |
| `scripts/verify_milestones.py` | 55/55, 0 discrepancies, 1 note, exit 0 | identical |
| `python3 triage.py fixtures/...` | 20 rows, exit 0 | identical |
| anti-overfit pattern scan | 27 patterns | 27, same names |

Diffed as full verbose output against the same saved baseline the module split
used, normalized only for the two expected identifier-prefix changes: test ids
gain `tests.`, and scanned pattern names gain `pipeline.`. Verifier and smoke
output needed no normalization and matched byte for byte. The pattern *names*,
not just the count, were compared against the pre-split `triage.py` again, so
Validate's three are still covered.

**Reference updates:** absolute imports inside `pipeline/` (`from
pipeline.constants import OK`), so a module reads the same whether imported by
the tests, `triage.py`, or `scripts/verify_milestones.py`; the verifier's
import repointed; and the fixture path in all four test files changed from
`Path(__file__).parent` to `.resolve().parent.parent`, which is the one edit
that would have broken every test at once had it been missed.

---

## M4 Dedup: rules signed off 2026-08-01

Five rules settled. MILESTONES.md's M4 section was rewritten to state them as
rules rather than proposals, same treatment M2's and M3's got, and the doc pass
ran as its own step before any code was written.

1. **Match key: `strip()` then lowercase, together**, over the whole address
   rather than the domain alone.
2. **Only `ok`-status emails participate in matching.** `missing` and
   `malformed` both yield `match_key = None`, and a `None` matches nothing,
   including another `None`. A data-quality gate, kept separate from rule 1's
   string normalization.
3. **"Earlier" means first occurrence in file order, never `submitted_at`.**
   M2 already declared that field unreliable for decisions and L-012's own
   value proves why; letting it order Dedup would hand it back a role the
   pipeline deliberately stripped from it everywhere else.
4. **Group membership is symmetric.** L-001 gets `linked_lead_ids: ['L-003']`,
   not just the reverse, so the earlier row is not forced to decide blind on
   information the pipeline already holds. Whether it *should* act on that is
   left to M5/M6.
5. **A group of 3+ rows sharing a key all link to the single first
   occurrence, not chained pairwise.** A star, not a chain, and not a clique:
   later members link to the first occurrence and not to each other, because
   what rule 4 is for is giving the first occurrence visibility into
   everything downstream of it.

**Cross-file staleness fixed in the same pass.** SPEC.md Section 5's open flag
on Dedup match confidence (`SPEC.md:171`) is resolved rather than left standing:
matching is exact, so confidence stops being a dimension of it at all, which is
why the question is answered by removing it rather than by picking a threshold.
Two neighbouring lines went stale the moment rule 4 was adopted and were
corrected with it: Section 5 said Dedup "flags a row as linked to an earlier
`lead_id`" and required the `reason` to name "the earlier `lead_id`", both of
which are only half true once links are symmetric, since a first-occurrence row
has no earlier row to name. MILESTONES.md's header status paragraph and its
sanctioned-generalization list (now `M2, M3, M4, M9`, with M4's narrow scope
written into the bullet) were updated in the same pass.

**One thing this milestone deliberately did not do:** the `lead_id` uniqueness
check SPEC.md Section 1 assigns to the Dedup stage. No M4 criterion covers it,
so it was left out rather than folded in quietly. Deferred to M5/M7 and
recorded under "Carried into M5" below, which is its durable home.

---

## M4: Dedup

**Files:** `pipeline/dedup.py` (`_match_key`, `dedup`, `dedup_stage_trace`), a `linked=`
column on `triage.py`'s smoke run, `tests/test_dedup.py` (33 tests, stdlib
`unittest`). No new dependency; `dedup` is plain dict-and-list work.

**Run it:**

```
python3 triage.py                      # ingest + validate + sanitize + dedup
python3 -m unittest tests.test_dedup -v
```

**What it does:** computes a match key per row from `email` (rules 1 and 2),
groups rows that share a non-`None` key, and returns one result per row in file
order carrying `match_key`, `is_duplicate`, `first_occurrence_lead_id`,
`linked_lead_ids`, and `linked_rows`. It mutates nothing and drops nothing:
duplicates do not collapse, every row keeps its own result, and every row still
reaches the Judge per the locked Pipeline rule.

**The two-shape return, decided rather than defaulted.** `linked_rows` carries
full row copies, not a curated subset of fields, so M5 can compare whatever it
turns out to need without M4 having pre-decided what matters. `stage_trace` gets
the thin view instead, via `dedup_stage_trace`, which is every field except
`linked_rows`: copying whole input rows into run_log.json would duplicate the
input record without adding a fact.

**Observed results** [observed, 2026-08-01, Python 3.11.4]:

- 33 of 33 M4 tests pass; 110 of 110 across all four stages.
- `scripts/verify_milestones.py`: **55 of 55 verified, 0 discrepancies, 1 note,
  exit 0**, up from 50 (five added: file order on both pairs, `submitted_at`
  order on both pairs, and largest-group-is-2).
- Links across all 20 rows: L-001 ↔ L-003, L-002 ↔ L-015, and **the other 16
  rows carry no link**. Asserted as an exact per-row map, so a spurious link
  anywhere fails.
- L-004 is the only row with `match_key = None`; the other 19 rows carry a key,
  17 of them distinct.

**A gap found by mutation testing, not by reasoning about the code, and then
closed.** Each of five deliberate breakages was applied to a scratch copy and
the suite re-run [observed]. Four went red where they should: one-directional
links (3 failures), ordering groups by `submitted_at` (1), dropping `strip()`
(2), dropping `lower()` (3). The fifth did not. **Deleting rule 2's `None`
guard from `dedup` entirely left all 27 tests green.** The cause was a fixture
property, not a missing assertion: L-004 is the only keyless row, so a group
built from `None` keys has exactly one member and produces no link either way.
No test written against these 20 rows as they stand can tell the guard from its
absence.

The untested behavior was not a corner case, which is what justified acting
rather than filing it. On a fresh batch with several blank emails, an absent
guard links every blank-email row into one false duplicate group, and those are
precisely the rows already carrying a data-quality problem.

**Closed by a second, separate generalization exception, signed off
2026-08-01.** Two real fixture rows run through the real `dedup()` with a
**simulated** Validate email status of `missing` or `malformed`. What is
synthetic is the status handed to the stage, which isolates `dedup()`'s
bucketing from whether Validate would really call those emails unusable; the
rows are unmodified fixture rows, and nothing fabricated is presented as real
fixture data. Same precedent as M6's simulated Judge output. It grants nothing
to rules 1 and 2's existing `_match_key()` scope, which is unchanged, and the
scope note sits in `NoneKeyBucketingTest`'s docstring so the boundary travels
with the code rather than living in this file alone.

`NoneKeyBucketingTest` covers the sharpest case (two rows that really do share
an address, kept apart only by the simulated status), two rows with different
addresses, a simulated row against the fixture's real keyless L-004, and three
unusable rows at once, which is the blank-email batch that motivated the
exception. One test guards the helper itself: the real L-001/L-003 and
L-002/L-015 pairs must still link, so a green result cannot come from having
broken `dedup`'s input.

**Re-mutated to confirm the new tests actually bite** [observed, 2026-08-01]:
deleting the guard again now fails **7 assertions across 4 tests**, where before
it failed none. The guard is also written structurally rather than as a later
filter, `None` keys never entering `groups` at all, so the code states the rule
independently of the test that now pins it.

**Rule 3 is checked structurally, because the fixture cannot check it.** On both
duplicate pairs `submitted_at` runs in the same direction as file order (L-001
09:14 before L-003 13:40; L-002 on 06-01 before L-015 on 06-05) [observed], so
an implementation that ordered groups by timestamp passes every data test in the
file. `FileOrderTest` therefore asserts that neither `dedup` nor `_match_key`
reads that field at all, following M3's AntiOverfitTest precedent, and separately
asserts the fixture property itself so a future fixture that reverses a pair
fails loudly instead of quietly leaving the structural test as the only evidence.
Both timestamp claims are now in the verifier as well.

**Two tests exist for defects that would otherwise be invisible.**
`test_misaligned_input_raises_rather_than_truncating` covers the alignment
between `rows` and `validations`: `zip()` would silently truncate to the shorter
list, which in this pipeline means dropping rows before the Judge, so `dedup`
raises instead. `test_linked_rows_are_copies` mutates a returned row and asserts
the fixture row is untouched, since `linked_rows` handing out live references
would let a later stage edit the input record the run log is supposed to
preserve.

**Rules 1 and 2 use the generalization exception at M2's narrow scope**:
synthetic values handed to `_match_key()` directly, never assembled into
fabricated lead rows. Necessary because both duplicate pairs are byte-identical,
so no real row varies in case or whitespace, and no fixture email is `malformed`.

**One known-untested item remains: rule 5's 3+ group.** The fixture's largest
shared-key group is two rows, so star-versus-chain is unobservable, and
observing it needs a fabricated third row, which neither sanctioned exception
permits. Recorded as an accepted gap rather than closed.

---

## Carried into M5

- **Whatever consumes `linked_rows` must do the consistent-versus-conflicting
  comparison inside the model's own reasoning, not in a helper function.**
  Comparing two rows' budget, company, and ask to decide whether they confirm
  or contradict each other is judgment, and a helper that pre-computed it would
  quietly recreate the judgment-in-pattern-code problem M4 avoided by leaving
  that call out of Dedup. SPEC.md Section 5's Duplicate rows bullets are the
  Judge's criteria, not Dedup's, and they stay that way.
- The `reason` on a linked row must name the linked `lead_id` explicitly, per
  SPEC.md Section 5. A first-occurrence row names the later `lead_id`(s) linked
  to it, since it has no earlier one to name.
- **`lead_id` uniqueness is unowned and needs a home in M5 or M7.** SPEC.md
  Section 1's schema table assigns the check to the Dedup stage, but M4's goal
  is email linking and no M4 criterion covers it, so it was deliberately left
  out rather than folded in quietly (settled 2026-08-01). All 20 lead_ids are
  distinct in this fixture [observed], so nothing rides on it today, and
  `dedup()` keys rows by position rather than by `lead_id`, so a duplicate one
  would not corrupt linking. Written down here rather than left in chat so it
  has a durable owner by the time M7 assembles the full run.

---

## M3 Sanitize: decisions signed off 2026-07-31

Four decisions settled. MILESTONES.md's M3 section was rewritten to state them
as rules rather than proposals, with the proposal language removed rather than
left standing beside the adopted rule, same treatment as M2's.

1. **Sensitive-content boundary: describing your own regulatory context does
   not fire; a legal or compliance demand directed at Single Grain does.**
   L-017 does not fire, L-019 does.
2. **Scanned fields: `message`, `name`, and `company`.** The criteria cite only
   `message`, but M5's prompt carries all three, so a message-only detector
   leaves an attack surface a fresh fixture could use.
3. **Sanitize detects and never mutates.** SPEC.md Section 1's `stage_trace`
   previously read "sanitization changes made," which implied rewriting lead
   text.
4. **Categories are independent, never first-match-wins.** All three detectors
   run on every field of every row.

**Cross-file staleness fixed in the same change**, so nothing contradicts
anything: SPEC.md Section 5's ESCALATE bullet no longer calls the
sensitive-content definition "still open," SPEC.md Section 1's `stage_trace`
now uses detection-only wording, and CLAUDE.md carries the decision-1
containment note under a new "Documented design decisions" heading rather than
leaving it in a planning message.

**A stale proposal was caught before code, not after.** MILESTONES.md's M3
still read "One open decision this milestone must settle... Flagging for
sign-off" for the sensitive-content boundary, and PROGRESS.md's status table
agreed. It was not treated as a default-yes, on the M2 precedent: that
milestone's budget-suffix proposal was flagged the same way and was **rejected**
when settled, flipping `15k` from unparseable to 15000. A flagged proposal here
carries no presumption either way.

---

## M3: Sanitize

**Files:** `pipeline/sanitize.py` (`SCANNED_FIELDS`, the rule patterns,
`detect_injection`, `detect_security_threat`, `detect_sensitive_content`,
`sanitize`), `pipeline/constants.py` (the three category names and
`CONTENT_CATEGORIES`), a `content=` column on `triage.py`'s smoke run,
`tests/test_sanitize.py` (37 tests, stdlib `unittest`). No new dependency; `re` is
stdlib and was already imported for M2.

**Run it:**

```
python3 triage.py                      # ingest + validate + sanitize, all 20 rows
python3 -m unittest tests.test_sanitize -v
```

**What it does:** runs all three detectors over `name`, `company`, and
`message` on every row, and returns SPEC.md Section 1's `content_flags`, a list
of `{category, description}` with one entry per category detected and the
description naming which field and which rule fired. It mutates nothing and
skips nothing.

**How the rules avoid being keyword matchers.** Almost every rule requires two
independent things to co-occur inside one sentence: an override verb *and* an
instruction noun, a payment asset *and* a demand verb *and* time pressure, a
data-request verb *and* a personal-data object. Single words carry no weight on
their own, which is what N1, N2, and N3 exist to prove. The one deliberate
exception is the pretext rule, which spans the whole message rather than a
sentence, because pretext is a two-part structure by nature: the relationship
claim sits in one sentence and the demand in the next, which is exactly how
L-020 is built.

**Observed results** [observed, 2026-07-31, Python 3.11.4]:

- 37 of 37 M3 tests pass; 77 of 77 across all three stages.
- `scripts/verify_milestones.py`: 50 of 50 verified, 0 discrepancies, exit 0,
  up from 47 (three L-013 claims added).
- Flags across all 20 rows: L-006 `injection`, L-019 `sensitive_content`,
  L-020 `security_threat`, and **the other 17 rows clean**. Asserted as an
  exact per-row map, not just for the three named rows, so a spurious fire
  anywhere fails.

**Bad output found and fixed: one word satisfied both halves of a
co-occurrence rule.** Recorded because it is the kind of defect this milestone
is most likely to ship. `overdue` and `past due` were listed under both
`_OBLIGATION` (the relationship-claim half of the pretext rule) and `_URGENCY`
(the demand half). A rule written to require two independent signals could
therefore be satisfied by one word appearing once, which collapses it straight
back into the keyword matching the design exists to avoid. Concretely: any
message mentioning an overdue invoice would have fired `security_threat` with
no demand, no urgency, and no link anywhere in it, which on a fresh fixture is
an ordinary customer chasing their own billing question. Caught by
`test_pretext_sentence_alone_does_not_fire`, which feeds the detector L-020's
first sentence alone and requires silence. Fixed by removing the obligation
markers from `_URGENCY`, where they never belonged: they describe a debt, not
time pressure. Both halves now draw on disjoint vocabulary, and the comment on
`_URGENCY` records why so it does not get re-added.

**Second defect, same class, found by asking whether the first fix
generalized.** The first fix was verified only by
`test_pretext_sentence_alone_does_not_fire`, which feeds the detector one
string, L-020's opening sentence, using the two words that caused the bug. That
proves those words are fixed and says nothing about the category. Sweeping the
whole obligation vocabulary against the whole urgency vocabulary [observed]
came back clean, 9 of 9 claim-only strings silent and 63 of 63 claim-plus-demand
combinations firing, but probing the closest surviving analogue found a second
instance one level deeper: `outstanding invoice` supplies the obligation claim,
and `invoice` is a payment asset too, so the same noun covered both halves and
only a common verb was left to complete the rule. Three ordinary billing
sentences fired as `security_threat`, including `Please send me the outstanding
invoice for last quarter.` On 500 real leads a week that is a customer asking
about their own bill, routed to a human as a suspected attacker.

Fixed by requiring the claim and the payment demand to come from **different
sentences**, which is what "two independent signals" was always supposed to
mean. Urgency and executable payloads stay message-level, since their
vocabulary shares nothing with the claim's and cannot double up. Fixing that
exposed a third, smaller slip in the same family: `wire` was in the
payment-asset list when it is the verb there, so an obligation claim followed
by `Wire the funds to the account below` was missed entirely, with no urgency
word or link to catch it. Assets and demand verbs are now strictly disjoint.

**Fourth defect, found by running the same audit against the other two
detectors.** The disjointness check had only ever been pointed at the rule
where a bug was noticed. Swept across all seven co-occurrence rules in all
three detectors, it found one more instance: `subject access request` sat in
`_LEGAL_CITATION`, and it contains the word "request", which satisfies
`_REQUEST_VERB`. One phrase covered both halves of the citation rule. The
visible consequence was a decision-1 violation: a vendor writing `our subject
access request process needs work` is describing its own regulatory context and
must stay clean, but fired `sensitive_content`. Fixed by removing the phrase
from the citation list and giving it its own rule that requires the request to
be *made of us* (`submitting`, `filing`, `lodging`), which is decision 1's
boundary applied to the one phrase that names the request type outright.

**Five more false positives, same audit, different mechanism.** These were not
double duty: both halves were genuinely separate tokens. They fired because
both halves are ordinary vocabulary *in this domain*, which is the part a
generic-looking rule hides. This pipeline reads marketing leads, so:

- `We need help to score and qualify inbound leads better.` fired `injection`.
  So did `Our sales team wants to classify leads as qualify or nurture
  automatically.` These are close to the most common sentences a genuine
  prospect writes, and `injection` caps confidence hardest of any category
  (`trust_risk` 0.2), so the cost of the error is the highest available.
- `We have full confidence you can help us qualify more leads.` fired
  `injection`.
- `We need someone willing to ignore the usual rules of SEO.` fired
  `injection`.
- `We want to remove personal data from our old funnel exports.` fired
  `sensitive_content`.

Each was fixed by adding the **third signal that was doing the real work all
along**, never by excluding a phrase:

- `instruction_override` now requires a scope marker (`previous`, `earlier`,
  `your`). Injection targets instructions the *reader* was given; a lead
  talking about rules is talking about its own industry.
- `assigns_its_own_decision` now requires a self-reference plus `as <decision>`,
  so naming a decision value is not enough, only assigning one to *this
  submission* is.
- `pins_its_own_confidence` now requires confidence supplied as a parameter
  (`with confidence 1.0`, `with full confidence`), which separates a supplied
  value from a sentiment about the agency.
- `data_subject_request` now requires the data to be ours to hold (`you hold`,
  `you have collected`, `about me`), which is what makes it a request against
  us rather than a lead's own data hygiene.
- `section N` left `_LEGAL_CITATION` entirely: RFPs and creative briefs are
  full of numbered sections. `article N` stays, being rare in business prose.

**Worth stating plainly against CLAUDE.md's tripwire**, which says that a rule
needing per-phrase exceptions has crossed into judgment and belongs in the
Judge. None of these five fixes is an exception list. Each adds a structural
requirement (directed at *us*, directed at *this submission*, scoped to the
*reader's* instructions) that encodes the distinction the category was always
about. That is the opposite of a per-phrase carve-out, and the tripwire has not
been tripped. If a future fix cannot be expressed that way, it should be.

`PretextVocabularyTest` makes the whole probe permanent rather than a one-off
run: the vocabulary sweeps in both directions, the three ordinary billing
sentences that must stay silent, and the separate-sentence payment demand that
must still fire, which is the coverage the fix could have quietly cost.
`CoOccurrenceDisjointnessTest` generalizes it to **all seven co-occurrence
rules across all three detectors**, asserting that no single phrase fires any
rule on its own, so the next instance of this defect fails a test the day it is
written rather than the day something happens to trip it.
`OrdinaryMarketingLeadTest` holds the nine prospect sentences above and asserts
all three detectors stay silent on every one, alongside the genuine versions
that must still fire, so narrowing cannot buy quiet by breaking detection.

**One rule ships covered by a synthetic that is not in MILESTONES.md.**
SPEC.md Section 5's security-threat bullet names extortion and threats of harm
alongside phishing and malware, and no fixture row and none of the four
approved variants exercises that branch. Rather than ship it untested or drop a
category SPEC requires, `test_sanitize.py` covers it with one local synthetic
(`X1`). Flagging because it is a test case chosen without sign-off.

**One test asserts row-level behavior against invented data**,
`MultiFieldScanTest.test_injection_hidden_in_the_company_field_is_detected`.
Proving decision 2 (that `sanitize` reads a field other than `message`) needs a
row with content in that field, and no fixture row has any. It runs under the
generalization exception MILESTONES.md's global constraint sanctions for M3 and
is kept to a single test; everything else synthetic in this milestone is passed
to a detector function directly, per M2's precedent.

**Anti-overfit constraint enforced rather than promised.** `AntiOverfitTest`
introspects every compiled pattern in all four stage modules (27 today: 24 in
`sanitize.py`, 3 in `validate.py`) and asserts none contains a lead_id or any
of 17 distinctive fixture literals (`fastpay`, `8823`, `brightcart`, and so
on). M3's non-negotiable constraint now fails a test instead of resting on
review. It scanned `triage.py` alone until the 2026-08-01 module split; see
that entry for why widening the scan was load-bearing rather than cosmetic.

---

## M2 Validate: decisions signed off 2026-07-31

Both parsing decisions that blocked M2 are settled. MILESTONES.md's M2 section
was rewritten to state them as rules rather than proposals, with the superseded
text removed rather than left standing beside the adopted rule.

1. **Budget shorthand: `k`/`K` is supported and multiplies by 1000; every other
   letter suffix is unparseable.** The earlier proposal, which rejected all
   letter suffixes and made L-017 unparseable, was considered and **not**
   adopted. **L-017's `15k` parses to 15000.** Recorded here because the two
   rules diverge downstream, not just at the parse: at 15000 L-017 clears
   SPEC.md Section 5 criterion 2's provisional $2000 floor, so it does not
   escalate on an unparseable budget, Section 6's `budget_signal` override does
   not fire on it, and its `data_completeness` is 1.0 rather than 0.8.
2. **"Malformed" scope for free-text fields: shape only, never plausibility.**
   L-010's `asdf@asdf.com`, company `asdf`, and message `asdfasdf` are all
   shape-valid and therefore not malformed, as is L-016's HTML-wrapped message.
   Whether they are meaningful is the Judge's call in M5, not Validate's.

Four smaller calls signed off with them:

- Whitespace-only cells count as missing on all five fields. No fixture row has
  one, so this is about the code path only.
- A blank `monthly_budget_usd` is reported `missing` and a present-but-
  non-numeric one `unparseable`. They stay distinct in M2 and are collapsed by
  M6, which is where SPEC.md Section 6 puts the single override trigger.
  Carried into M6's acceptance criteria so it cannot be lost in the handoff.
- The `malformed` branch is covered by synthetic values passed to the per-field
  checkers directly, never assembled into fabricated lead rows. Necessary
  because no field in any of the 20 fixture rows is malformed under decision 2.
- **Three** email-domain signals belong to M2 and are part of `validate()`'s
  output: `email_domain_is_personal_provider`, `is_disposable_email_domain`,
  and `is_reserved_or_example_domain`. SPEC.md Section 5's design note requires
  them be computed deterministically before M5 so they do not become LLM-side
  regexes, and no milestone owned any of them until now. The first was signed
  off with the parsing decisions; the other two were signed off after M2's
  first pass surfaced them in the fixture and flagged them rather than folding
  them in.

  **Kept as three distinct signals, not one merged "bad domain" flag**, on the
  grounds that they mean different things under SPEC.md Section 5 criterion 1's
  unverifiable-versus-fabricated split, which is the criterion's whole purpose.
  Consumer webmail is the textbook *unverifiable* case: a real person with no
  company domain to offer. A disposable inbox says someone is deliberately
  avoiding contact. A placeholder domain says no party is behind the value at
  all, which points at *fabricated*. Merging them would collapse a signal
  pointing one way and a signal pointing the other into the same bit.

**M2's input contract, from M1.** `ingest()` returns a list of dicts, one per
row, in file order, every value a raw string with nothing stripped, coerced, or
unescaped. On this fixture every row carries exactly the 9 schema columns, but
`ingest()` deliberately does not enforce that per row: a ragged row would arrive
with surplus cells under `_extra_fields` or absent ones as `None`. Classifying
that is M2's job. Ingest's only hard failure is a header that does not match
`SCHEMA`.

**Verifier, re-run after the MILESTONES.md rewrite** [observed, 2026-07-31]:
`python3 scripts/verify_milestones.py` reports 41 of 41 verified, 0
discrepancies, 1 note, exit 0, unchanged. No claim in it needed editing, and
that is the correct outcome rather than a missed update: its M2 claims assert
raw fixture values (`L-017.monthly_budget_usd == '15k'`), not derived
classifications, and decision 1 changes how `15k` is interpreted, not what the
cell contains. CLAUDE.md's update rule triggers on a changed cited value or a
new criterion citing one, and neither happened. The derived outcome, that `15k`
becomes 15000, is asserted in `test_validate.py` where it belongs; putting it
in the verifier would blur what that script is for.

---

## M2: Validate

**Files:** `pipeline/validate.py` (`CRITERIA_FIELDS`, `DOMAIN_SIGNALS`, three domain
lists, five per-field checkers, `validate_budget`, the three domain-signal
functions over one `_email_domain` helper, `check_submitted_at`, `validate()`),
`pipeline/constants.py` (the four status constants), an extended `__main__` smoke run in
`triage.py`, `tests/test_validate.py` (33 tests, stdlib `unittest`). No new
dependency; `re`, `unicodedata`, and `datetime` are stdlib.

**Run it:**

```
python3 triage.py                      # ingest + validate, all 20 rows
python3 -m unittest tests.test_validate -v
python3 -m unittest discover -p "test_*.py" -v
```

**What it does:** classifies each row's five criteria-feeding fields as `ok`,
`missing`, `malformed`, or `unparseable`, parses the budget to a number,
computes the three email-domain signals, and checks `submitted_at` for
crash-safety only. It returns a separate result dict and mutates nothing, and
it classifies every row rather than dropping any, per the locked Pipeline rule.

**Observed results** [observed, 2026-07-31, Python 3.11.4]:

- 33 of 33 M2 tests pass; 40 of 40 across both stages.
- `scripts/verify_milestones.py`: **47 of 47 verified, 0 discrepancies, 1 note,
  exit 0**, up from 41 claims (six added, see below).
- Field statuses across all 20 rows: 1 `missing` email (L-004), 6 `missing`
  websites, 4 `missing` companies, 1 `missing` message (L-018), 1
  `unparseable` budget (L-005). **Zero `malformed` anywhere.**
- L-017's `15k` parses to 15000, per decision 1.
- Each domain signal fires on exactly one row and the three do not overlap:
  L-008 consumer webmail, L-013 disposable inbox, L-019 placeholder domain.
  L-004 is `None` on all three, and the remaining 16 rows are `False` on all
  three.

**The `malformed` branch has no real-row coverage, by nature of the fixture.**
Not a gap in the tests, a fact about the data: under the shape-only rule every
non-blank email is `local@domain.tld`-shaped, every non-blank website is a
well-formed `http(s)://` URL, and no company or message carries control
characters. `test_no_fixture_field_is_malformed` asserts this emptiness
directly rather than leaving it implicit, so a future fixture that does contain
a malformed value fails there first instead of drifting silently.
`MalformedValueTest` covers the branch with synthetic *field values* passed to
the checker functions, never assembled into fabricated lead rows, so no
row-level behavior is asserted against invented data. That is the M2 exception
MILESTONES.md's global constraint sanctions, used at the narrowest scope that
still covers the branch.

**The same reasoning applies to the domain signals, for a different reason.**
Each fires on exactly one fixture row, so real rows prove the signals fire but
prove nothing about whether the rules behind them generalize, which is the
concern M3's non-negotiable constraint raises about detectors keyed to this
fixture's exact values. `DomainSignalRuleTest` probes the rules with synthetic
email addresses under the same sanction and the same scope limit: addresses
handed to the signal functions, never assembled into rows.

**Six claims added to `scripts/verify_milestones.py`** [observed]: M2's
domain-signal criteria assert that each signal fires on exactly one row, that
the three do not overlap, and that the remaining 16 non-blank-email rows are
False on all three. Those rest on which domains the fixture actually contains,
and nothing in the script covered that, so the 17 distinct domains are now
transcribed by hand and re-derived from the file, alongside per-signal checks.
Every list there is hand-written, including a second copy of the placeholder
rule: importing `PERSONAL_EMAIL_DOMAINS`, `DISPOSABLE_EMAIL_DOMAINS`, or
`RESERVED_TLDS` from `pipeline/validate.py` (`triage.py` before the 2026-08-01 split)
would make the script agree with the code by construction, which is the same
failure as parsing MILESTONES.md.

**Correction: `example.de` is not an RFC 2606 reserved domain.** Recorded
because it changed the implementation, not only the wording. An earlier note in
this file and in the verifier called L-019's domain RFC 2606 reserved. RFC 2606
reserves only the three literal names `example.com`, `example.net`, and
`example.org`; RFC 6761 separately reserves the `.test`, `.invalid`,
`.example`, and `.localhost` TLDs, and RFC 6762 reserves `.local`. `example.de`
is an ordinary ccTLD registration that follows the same placeholder convention
without being covered by any of them. So `is_reserved_or_example_domain` cannot
be a membership test against a reserved-name list; it needs a second rule for
the convention, and it has one. Both rules are stated in M2's criteria and
duplicated by hand in the verifier.

**Two boundaries on that second rule, both asserted in the tests so neither
becomes a surprise later.** It matches a two-label domain whose first label is
`example`, which covers RFC 2606's three literals for free. Capped at two
labels on purpose: `example.mycompany.com` is a real subdomain of a real
company, not a placeholder, and telling the two apart in general needs a public
suffix list, which 20 rows do not justify. The accepted gap is a placeholder
under a multi-part suffix such as `example.co.uk`, which returns False.
`test_reserved_signal_boundaries` asserts both cases directly rather than
leaving the limit implicit in a comment.

**Known untested path:** a ragged CSV row. `validate()` handles both shapes M1
documented, a `None` value from a short row classifying as `missing` and a
`_extra_fields` key surfacing as `extra_fields`, and `test_no_fixture_row_is_ragged`
confirms no fixture row is ragged. Exercising the path end to end needs a
malformed CSV file, which is synthetic row-level data, so it stays untested
here for the same reason M1 left its header-mismatch `ValueError` untested.

---

## M1: Ingest

**Files:** `pipeline/ingest.py` (`SCHEMA`, `EXTRA_FIELDS_KEY`, `ingest()`), the
`__main__` smoke run in `triage.py`, `tests/test_ingest.py` (7 tests, stdlib
`unittest`).

**Run it:**

```
python3 triage.py                      # defaults to fixtures/inbound_leads.csv
python3 triage.py <path-to-csv>
python3 -m unittest tests.test_ingest -v
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
