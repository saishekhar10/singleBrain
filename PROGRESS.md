# PROGRESS.md

Build status for the Lead Triage Agent. Milestone definitions live in
MILESTONES.md; this file records what is actually built, what running it
produced, and what that turned up. Numbers are labeled per brief.md
requirement #4.

| Milestone | Status |
|---|---|
| M1 Ingest | **Done**, signed off 2026-07-31 (7/7 tests green) |
| M2 Validate | **Built**, 33/33 tests green, awaiting sign-off (all parsing and signal decisions signed off 2026-07-31) |
| M3 Sanitize | **Built**, 37/37 tests green, awaiting sign-off (all four decisions signed off 2026-07-31) |
| M4 Dedup | Not started (acceptance criteria corrected, see below) |
| M5 Judge | Not started |
| M6 Guardrails | Not started |
| M7 Full run | Not started |
| M8 Manual comparison | Not started |
| M9 Red-team pass | Not started |
| M10 Validator loop | Not started |

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

**Files:** `triage.py` (three category constants, `CONTENT_CATEGORIES`,
`SCANNED_FIELDS`, the rule patterns, `detect_injection`,
`detect_security_threat`, `detect_sensitive_content`, `sanitize`, and a
`content=` column on the smoke run), `test_sanitize.py` (37 tests, stdlib
`unittest`). No new dependency; `re` is stdlib and was already imported for M2.

**Run it:**

```
python3 triage.py                      # ingest + validate + sanitize, all 20 rows
python3 -m unittest test_sanitize -v
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
introspects every compiled pattern in `triage.py` and asserts none contains a
lead_id or any of 17 distinctive fixture literals (`fastpay`, `8823`,
`brightcart`, and so on). M3's non-negotiable constraint now fails a test
instead of resting on review.

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

**Files:** `triage.py` (the four status constants, `CRITERIA_FIELDS`,
`DOMAIN_SIGNALS`, three domain lists, five per-field checkers,
`validate_budget`, the three domain-signal functions over one `_email_domain`
helper, `check_submitted_at`, `validate()`, and an extended `__main__` smoke
run), `test_validate.py` (33 tests, stdlib `unittest`). No new dependency;
`re`, `unicodedata`, and `datetime` are stdlib.

**Run it:**

```
python3 triage.py                      # ingest + validate, all 20 rows
python3 -m unittest test_validate -v
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
`RESERVED_TLDS` from `triage.py` would make the script agree with the code by
construction, which is the same failure as parsing MILESTONES.md.

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
