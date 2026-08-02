# Lead Triage Agent: Spec

Brief version: 2026-07. Sources: brief.md, scoring_rubric.md (Public Review Guide), SCORING.md, validate_submission.py.

Note on sourcing: the program-level README (referenced by validate_submission.py and by brief.md's packet requirements) is `BEAT_CLAUDE_README.md` in this repo, read in full for this draft. This is distinct from brief.md/scoring_rubric.md (challenge-specific) and from the README.md we'll write for our own submission later in Phase 7. Section 3 below cites it directly.

## 1. I/O Contract

### Input: fixtures/inbound_leads.csv

Only the header row has been seen so far, not the data. Columns, in order:

| Column | Presumed type | Notes |
|---|---|---|
| lead_id | string | Presumed unique key per row. Uniqueness is not assumed: duplicates are a named seeded trap, so the Dedup stage checks this rather than trusting it. |
| submitted_at | string (timestamp) | Exact format unconfirmed until real rows are read. |
| name | string | Contact name. |
| email | string | Contact email. Well-formedness is a Validate-stage concern, not assumed here. |
| company | string | |
| website | string (URL) | |
| monthly_budget_usd | string or numeric | Numeric-ness, sign, and range are Validate-stage concerns, not assumed here. |
| message | string (free text) | The field most likely to carry adversarial or injected instructions. Always treated as data, never as instructions, at every stage. |
| source | string | Presumed lead-source channel or category (e.g. "website", "referral"). Allowed values unconfirmed. |

Validation rules for each column (what counts as malformed, what's required vs. optional) are deliberately not defined here. That is Validate-stage logic, and depends on the real data, which hasn't been read yet. This table is a schema placeholder, not a validation spec.

### Output: decisions.csv

One row per input row. (Whether duplicates collapse to one output row or each gets its own is a Dedup-stage decision, not made here.) Exactly four columns, matching brief.md requirement #2 with no additions:

| Column | Type | Constraint |
|---|---|---|
| lead_id | string | Must equal an input lead_id exactly. |
| decision | string (enum) | Exactly one of: QUALIFY, NURTURE, REJECT, ESCALATE. Uppercase, no other values. |
| reason | string | One sentence. |
| confidence | float | Range [0.0, 1.0]. |

### Output: run_log.json

Purpose: this is the run's Tier 3 evidence (SCORING.md: "Logs or source records... prompt traces... or similar") and the backbone of the AI Usage Disclosure. A reviewer should be able to open this file and trace every decisions.csv row back to the exact prompt and response that produced it. That makes SCORING.md's "fabricated run" failure mode (decisions that don't match what the described agent would produce) checkable, not just claimed.

**Pipeline rule, locked:** every row reaches the Judge (LLM) stage. No exceptions, and no deterministic stage (Validate, Sanitize, Dedup) may pre-emptively skip or short-circuit a row before the Judge call runs. Guardrails is a post-hoc stage: it runs after the Judge call and may override the Judge's output, but it is never a reason a row skips the Judge entirely. This is deliberate: scoring_rubric.md notes reviewers check the row carrying adversarial content first, specifically for whether it produced a real model response rather than getting hard-coded away, so no deterministic stage may ever be the thing that keeps a row from reaching the Judge, whichever row that turns out to be.

Top-level shape:

```
{
  "run_metadata": { ... },
  "rows": [ { ... }, ... ]
}
```

`run_metadata` (once per run, not per row):
- `run_timestamp`
- `brief_version` ("2026-07")
- `fixture_checksum` (sha256 of fixtures/inbound_leads.csv)
- `fixture_row_count`
- `model` (name and version of the LLM used for the Judge stage)
- `script_version` (git commit hash or similar, so a re-run can be tied to the exact code that produced it)

`rows[]` (one entry per input row, correlated to decisions.csv by `lead_id`):
- `lead_id`
- `stage_trace`: what each of Validate, Sanitize, and Dedup found on this row (validation errors, content categories Sanitize detected and in which field, dedup match found and against which lead_id). These stages annotate the row; none of them may skip it past the Judge. **Sanitize detects and never mutates** (settled 2026-07-31, M3): it makes no changes to lead text, so there are no "sanitization changes" to record here. The defense against injected instructions is M5's labeled data boundary, not rewriting the input, and rewriting it would corrupt the honest record `llm_call` exists to preserve.
- `content_flags`: list, one entry per Sanitize-stage content category detected on this row, empty if none. Each entry is `{category, description}`, `category` one of `injection`, `security_threat`, `sensitive_content`, matching Section 6's `trust_risk` categories exactly. More than one can fire on the same row; `trust_risk`'s priority-order formula (Section 6) picks the most severe one present to set the score, but this field records everything Sanitize actually found, not just the one driving the score, so a reviewer can see the full picture. Detecting any of these does not skip the Judge call, per the Pipeline rule above, they're passed through as context.
- `llm_call`: always present, exactly one per row, every row reaches the Judge regardless of what upstream stages found. Full prompt sent, timestamp, and the full raw response. The raw response is structured: `decision`, `reason`, and the three Judge-scored confidence sub-fields defined in Section 6, each an object with `score` (0-1) and `reason` (one line): `identity_verifiability`, `budget_signal`, `need_clarity`. An actual prompt and response trace, not a summary of one.
- `guardrail_override`: present only if Guardrails changed the *decision* after the Judge call. What the Judge returned, what it was overridden to, and why. Absent when the Judge's decision ships as-is. Decision override only, confidence aggregation is a separate, always-present computation, see `confidence_scoring` below.
- `confidence_scoring`: always present, computed in Guardrails per Section 6, not by the Judge. Records:
  - `judge_scores_used`: the actual `identity_verifiability`, `budget_signal`, and `need_clarity` values fed into `weighted_average`, each `{value, source, reason}` where `source` is `judge` (taken from `llm_call`'s raw response as-is) or `override` (forced per Section 6, "When the underlying field can't be evaluated at all"). These can differ from `llm_call`'s raw response when an override applied, that's the point: `llm_call` is the honest record of what the Judge said, `judge_scores_used` is what the math actually ran on, and a reviewer needs both to hand-verify `weighted_average` from the log.
  - the two deterministic sub-scores, `data_completeness` and `trust_risk`, each alongside the flags or count that produced it
  - `weighted_average`, with the four values and weights shown, not just the result
  - whether the `trust_risk` cap was binding
  - the resulting `final_confidence`
- `final_decision`, `final_reason`, `final_confidence`: what actually ships in decisions.csv, i.e. the Judge's decision unless `guardrail_override` is present, in which case the overridden value; `final_confidence` must equal `confidence_scoring.final_confidence`. Must match the corresponding decisions.csv row exactly.
- `processed_at`

Exact shapes for `stage_trace` and `llm_call` are intentionally left loose until the pipeline stages themselves are designed. This is the contract other stages write to, not the stage implementation.

## 2. Non-Goals

Scope stays bounded to what a 20-row triage task, run once, actually needs. Everything below is deliberately not built, each would be solving a problem this task doesn't have:

- **No agent framework** (LangChain, LangGraph, CrewAI, AutoGen, etc.). A single deterministic pipeline with one LLM call per row doesn't need an orchestration abstraction on top of plain function calls. It would add a dependency and a learning curve for no behavioral benefit here.
- **No vector store or database.** Nothing in this task needs semantic retrieval or persistence across runs. Input is a CSV, output is a CSV and a JSON log, and every run is self-contained.
- **No multi-agent orchestration library.** This specifically means no framework where separate components pass messages to each other or spawn sub-agents autonomously (LangGraph, CrewAI, AutoGen, etc., the same category as above, called out on its own because it's the one most tempting to reach for here). This does **not** mean avoiding decomposition. The six-stage pipeline (Ingest, Validate, Sanitize, Dedup, Judge, Guardrails) stays as distinct, single-purpose components, implemented as plain functions called in sequence from a single entry point. Decomposing into stages is good design; wrapping those stages in an orchestration framework is the unnecessary part. **Corrected 2026-08-01, recorded rather than edited silently because the old wording was signed off:** this sentence read "called in sequence from one script" until `triage.py` was split into one module per stage, which then moved into a `pipeline/` package (`pipeline/ingest.py`, `validate.py`, `sanitize.py`, `dedup.py`, plus `constants.py` for vocabulary the stages share, with `judge.py`, `prompts.py`, and `guardrails.py` to follow), tests into `tests/`. The correction is to the mechanism only and the Non-Goal is unchanged: still plain functions, still called in sequence, still no framework, no orchestration library, and no components passing messages to each other or spawning anything. A package is a directory, not an abstraction: nothing in `pipeline/__init__.py` runs a stage or decides an order. `triage.py` remains the single entry point at the repo root and the documented run command in Section 3.
- **No retry/backoff infrastructure.** This runs once, interactively, over 20 rows. If an LLM call fails, that's visible immediately and can be rerun by hand. Exponential backoff, circuit breakers, and queuing solve a production-scale reliability problem this task doesn't have.
- **No UI.** The deliverable is decisions.csv and run_log.json, files a reviewer reads directly. A UI would just be another layer between the reviewer and the same information.

## 3. Artifact Access (placeholder, not finalized)

BEAT_CLAUDE_README.md, "Required Submission Packet," item 7, defines this section as: "working links, permissions, sample data, no-login demo instructions, and any setup notes needed for review."

For a local Python script, "no-login, runnable in under 5 minutes" likely requires:

- A pinned, minimal dependency list (stdlib plus one LLM SDK), installable with a single command.
- fixtures/inbound_leads.csv already checked into the repo, so no separate data download or access grant is needed.
- A documented single command to run the full pipeline (e.g. `python3 triage.py fixtures/inbound_leads.csv`).
- A stated Python version.
- An open question, not resolved here: the Judge stage needs an LLM API key, and "no-login" is in tension with "needs a reviewer's own API key." Options to weigh later: the reviewer supplies their own key via an environment variable, or the submission ships pre-generated decisions.csv and run_log.json so the reviewer can inspect a real run without needing to execute one themselves (brief.md allows this: it lists the decisions file and run log as deliverables separate from re-running the agent).

Not finalizing further until the pipeline is built and its actual runtime and dependencies are known.

## 4. What Stays Human

Placeholder. To be filled in once the guardrail layer exists and it's clear which rows the deterministic stages hard-escalate versus which the Judge stage decides.

## 5. Decision Taxonomy

Defines what each of the four decision values actually means, as a concrete test rather than a one-line description. This is the rubric the Judge (LLM) stage evaluates against in M5. It does not touch confidence scoring, that's separate and comes next. Written without reference to the fixture data itself: only the column header has been read so far, consistent with holding off until the manual pass over real rows is done.

**Design note, flagged per CLAUDE.md's standing rule on judgment vs. hardcoded logic:** criterion 1 below turns on whether an email domain is a personal or free consumer provider (gmail.com, yahoo.com, etc.). That's pattern detection, not judgment, so per CLAUDE.md it belongs in deterministic Python (Validate or Sanitize stage), producing a plain signal such as `email_domain_is_personal_provider: true/false` that gets handed to the Judge as a fact. The Judge applies the "verifiable identity" judgment using that signal plus the rest of the row; it does not itself pattern-match domains against a provider list. Flagging this now so it doesn't quietly turn into an LLM-side regex later.

### Evaluation order

Check ESCALATE's conditions first, including the cross-row conflict check under Duplicate rows below once Dedup has flagged a match. They describe cases where criteria 1 to 3 below can't be reliably evaluated at all, not cases where they were evaluated and failed, and this holds even on a row that otherwise reads as obvious junk; see the ordering note under ESCALATE for why. If none of those conditions apply, evaluate the three QUALIFY criteria. If all three pass, QUALIFY. If criterion 1 (identity) is the one failing, apply its unverifiable-vs-fabricated sub-test below rather than defaulting to REJECT or NURTURE. If criterion 2 or 3 fails cleanly instead (the data needed to judge it is present and readable, it just doesn't clear the bar), distinguish REJECT from NURTURE per their tests below.

### QUALIFY

Requires all three, together. Any one alone is not enough.

1. **Verifiable company identity.**
   Test: `email`'s domain is not a personal or free consumer provider, and the row gives an independent way to confirm that domain belongs to the claimed `company` (a matching or plausibly related `website` domain, or the email domain itself being the company's own domain).
   Fails when: the email is from a personal provider and there is no independently checkable company domain to fall back on (website missing, blank, or not a real-looking domain). A personal email plus an unverifiable "I work at X" claim in the message text does not clear this bar.

   **Failing alone splits into two outcomes, not one:**
   - **Unverifiable, routes to ESCALATE, not REJECT:** nothing about the company, budget, or ask is actively implausible or contradicted, there's just no domain to check it against (personal email, no website, a plausible-sounding company name), and budget and ask both pass on their own terms. This could be a real freelancer or small business without a fitting company domain; the pipeline can't tell, and an automated REJECT here would throw away a possibly-real prospect on the strength of one absent field. A human resolves it. This description assumes `company` itself has some name in it to weigh as plausible-sounding. The Judge still makes its best unverifiable-vs-fabricated call when `company` is blank too, using whatever else the row has, but Section 6 treats `identity_verifiability`'s confidence score as unassessable in that specific case, not merely low, since there's no company claim left to calibrate a genuine confidence read against. That's a statement about the confidence sub-score, not the decision itself, see Section 6, "When the underlying field can't be evaluated at all."
   - **Fabricated, routes to REJECT:** the claimed identity is actively implausible or contradicted, not just unconfirmed, e.g. the company name is nonsense or generic filler, a stated domain resolves to something unrelated, or the message itself undercuts the claim. Here the row isn't unconfirmed, it's confidently not real.

2. **Budget at or above the minimum floor.**
   Test: `monthly_budget_usd` parses to a number at or above the threshold.
   THRESHOLD: $2000/mo. **[Assumed], PROVISIONAL, not locked.** The fixture rows haven't been read yet; this is a placeholder pending the manual pass over real data, and it's explicitly open to revision once that's done. Nothing downstream should treat $2000 as settled.

3. **Decidable service ask.**
   Test: `message` states what they want clearly enough that a reasonable person could act on it without guessing (a specific service, outcome, or problem is named). A vague "let's talk," or a message that never says what's being asked for, fails this regardless of identity or budget.

### REJECT

Test: the row shows no evidence of genuine commercial intent, and no genuine content of any other kind either. The message is spam, unrelated junk, an obvious joke or test submission, or gibberish, not a real communication from a real person about anything. Or, every one of the three QUALIFY signals is absent or clearly fabricated, not merely unconfirmed (see the fabricated sub-case under criterion 1 for what "clearly fabricated" means for identity specifically). This is the "nothing real to work with" bucket, distinct from a real prospect who just doesn't clear the budget bar, distinct from a prospect whose identity simply can't be confirmed, and distinct from a genuine, non-sales communication that still needs a human response (a complaint, a support request, a misdirected inquiry), see the ESCALATE bullet below, that's real content, just not a sales lead, and doesn't belong here either.

### NURTURE

Applies when identity (criterion 1) passes, and exactly one of budget or ask fails on its own terms: known and readable, just not there yet, not missing or contradicted.

- **Budget short:** identity and ask both pass, but the budget figure is present and readable, just below threshold, or the message itself signals it's premature ("exploring options for later," "budget not approved yet").
- **Ask underspecified:** identity and budget both pass, but the message doesn't state a clear, decidable ask, while still reading as a genuine inquiry rather than junk (e.g. "we'd love to work together, let's talk" with no service or problem named). Same logic as the budget case: a vague-but-genuine ask is a follow-up problem (find out what they need), not a data-trust problem, so it doesn't need a human the way an unverifiable identity does.

Identity failing alone does not land here, see the unverifiable/fabricated split under QUALIFY criterion 1. The dividing line from ESCALATE in both cases above: the failing criterion's data is known and read, just insufficient, not missing, unparseable, or contradicted.

Rows where more than one criterion fails at once aren't enumerated case by case here; the Judge weighs them against the definitions above (does the shortfall read as genuine-but-incomplete, or as implausible/fabricated) rather than following a lookup table for every combination.

### ESCALATE

Test: any of the following, checked before criteria 1 to 3 are evaluated:
- A field needed to evaluate criteria 1, 2, or 3 is missing, malformed, or unparseable (budget present but not a valid number, email empty or not a valid address shape), such that the criterion can't be evaluated at all, not just that it fails. Scope note: this only covers fields that feed criteria 1 to 3 (`email`, `website`, `company`, `monthly_budget_usd`, `message`). A malformed field the taxonomy doesn't use for QUALIFY, `submitted_at` for instance, doesn't trigger this clause on its own.
- The message is genuine and legible, but isn't a sales inquiry at all: a complaint, a support request, a partnership, press, or legal inquiry, a job application, or similar, submitted through this form. Test: does the message reflect a real communication a reasonable business would want a human to see and act on, even though it's not asking to buy anything? If yes, this routes to ESCALATE, not REJECT: REJECT is for content with nothing real behind it, and this has something real behind it, just not something the QUALIFY/NURTURE/REJECT criteria, built to evaluate sales intent, can meaningfully adjudicate. Auto-discarding it would silently drop something that needs a response; this pipeline doesn't make that call automatically.
- Two fields conflict in a way that can't be resolved from the row alone (stated budget contradicts what the message describes, company name contradicts the domain in `email` or `website`).
- The message contains sensitive content that shouldn't be auto-decided. **Definition settled 2026-07-31 (M3), no longer open:** a business describing its *own* regulatory context does not count; an actual legal or compliance demand directed at Single Grain does. A demand means a data-subject request (delete, erase, disclose, provide, access) against personal data, a legal or regulatory citation paired with a request or a threat, or a threat of legal action. "We need ad copy that clears our compliance review" is the first case and does not fire. "Delete the personal data you hold on me under GDPR Article 17" is the second and does.
- The message contains security-threat content: a phishing attempt or suspicious link asking the reader to click through or enter credentials, a malware or malicious-attachment reference, an extortion attempt, or an explicit threat of harm to the business or the reader. Distinct from sensitive content above, which is a privacy or compliance exposure, not hostility, and from injection or manipulation content below, which targets the agent's own behavior rather than the business or the reader.
- The message contains apparent injection or manipulation content directed at the agent itself. Per the pipeline rule locked in Section 1, this does not skip the Judge call: the Judge still evaluates the row on its underlying merits and separately flags the manipulation attempt. ESCALATE here is a judgment call about whether a human should review the row, not an automatic reflex to the mere presence of injected text. It is also not the pipeline's final word: Guardrails (Section 1, M6) runs after the Judge and can still override this decision in either direction. This section describes what the Judge evaluates, not what the pipeline ultimately outputs.

**On ordering, decided explicitly:** because ESCALATE is checked first, a row that otherwise reads as obvious junk but has a broken field feeding criteria 1 to 3 (a garbled budget value on a spammy-looking message, say) escalates rather than auto-rejecting. This is intended, not a side effect of check order. "Looks like junk" is a pattern-matched impression, and when the underlying data is actually broken, that impression can't be verified. brief.md is explicit that malformed input should route to a human rather than get a confident automated answer, and REJECT is still a confident, unreviewed call, so this pipeline doesn't let "the row looks bad anyway" substitute for readable data as the basis for making it. The scope note above limits the blast radius to fields that actually matter for QUALIFY, so this isn't every malformed field in the row, only the ones feeding the decision. The tradeoff is more ESCALATE volume on rows that are, in fact, junk. That's accepted here; worth watching in the manual pass, and if it fires constantly on genuinely obvious spam that's a signal to revisit, but the default favors a human catching a real trap over the pipeline confidently discarding one.

This is the "can't tell, and guessing would be worse than asking" bucket: distinct from REJECT (the row is readable and the answer is no) and NURTURE (the row is readable and the answer is not yet).

### Duplicate rows

Dedup links rows that share an `email`. The link is symmetric (M4 rule 4): a later row is flagged as linked to the first occurrence, and the first occurrence is flagged as linked to every later row, so neither side of a pair reads it blind. "Earlier" throughout this section means first occurrence in file order, never `submitted_at`. Once flagged, the row still goes through the full evaluation above on its own content, same Pipeline rule as every other row, no special-casing that skips the Judge or the criteria.

- **Consistent with the linked lead** (matching identity signals, and budget/ask that's the same or doesn't contradict the other submission): decide the row on its own merits, exactly like any other row. In practice this usually lands both rows on the same decision, since the content is the same or compatible, that's a consequence of evaluating each honestly, not a special "duplicates get decision X" rule. The `reason` must state the duplicate relationship and the linked `lead_id` explicitly, so it's visible in decisions.csv itself, not just in run_log.json's `stage_trace`. A first-occurrence row names the later `lead_id`(s) linked to it, since it has no earlier one to name.
- **Conflicts with the linked lead** (different budget, different company, a materially different ask, anything that contradicts rather than confirms): ESCALATE. This is the cross-row version of the field-conflict bullet above: two submissions claiming to be the same lead but disagreeing with each other is exactly the kind of thing that can't be resolved from the rows alone.

**Settled 2026-08-01 (M4), no longer open:** how confident Dedup's matching needs to be before treating two rows as linked. Matching is exact on a normalized `email` key, `strip()` plus lowercase, and only an `ok`-status email produces a key at all: a missing or malformed one yields no key and matches nothing, including another keyless row. Fuzzy or similarity matching is out of scope. Confidence therefore does not arise as a dimension of Dedup's matching, which is why the question is answered by removing it rather than by picking a threshold: a match is present or absent, and this section's assumption that a match is trustworthy once made holds by construction. Two further rules matter to this section's reading of a linked row: "earlier" means first occurrence in file order and never `submitted_at`, which M2 declared unreliable for decisions; and linking is symmetric, so the earlier row carries the link too rather than being left blind. What Dedup does not decide is whether two linked rows are consistent or conflicting. That is a reading of the two rows' content, it belongs to the Judge under the two bullets above, and M4 deliberately leaves it there rather than computing it deterministically. See MILESTONES.md's M4 section for the rules in full.

## 6. Confidence Scoring

Defines how `confidence` in decisions.csv is computed. The Judge returns three sub-scores that require actually reading the row, this is genuine LLM judgment, the same three calls Section 5 already asks it to make, just returned as explicit scored fields with a one-line reason instead of collapsed into one opaque number. Two more sub-scores are computed deterministically from Validate and Sanitize-stage flags and merged in afterward, not asked of the Judge at all. Aggregation into `final_confidence` happens in Guardrails (M6), the same stage that already owns post-hoc decision overrides per Section 1, not in the Judge. Scope for M5 (Judge prompt) and M6 (Guardrails aggregation), not implementation.

### The three Judge-scored sub-scores

Each pairs a 0-1 score with a one-line reason.

1. **`identity_verifiability`.**
   Test: how confident is the Judge in whichever of the three Section 5 criterion 1 outcomes it landed on (verifiable, unverifiable, fabricated)? A clean case, an obviously-real company domain or an obviously-fake claim, scores high in either direction. A genuinely borderline case (plausible name, no domain, could reasonably go either way) scores low, even though the Judge still has to commit to one bucket to make the QUALIFY/ESCALATE/REJECT call.

2. **`budget_signal`.**
   Test: not the pass/fail threshold check from Section 5 criterion 2, that's a separate, simpler numeric comparison. This is a plausibility read: does `monthly_budget_usd` look proportionate and consistent with the rest of the row (the scale implied by the message, the specificity of the ask), or does it look like a placeholder, a suspiciously round number, or an entry error unrelated to what's actually being asked for? A row can clear criterion 2's threshold and still score low here if the number itself looks fabricated.

3. **`need_clarity`.**
   Test: how confident is the Judge in its Section 5 criterion 3 decidable-ask call? A message that clearly states, or clearly fails to state, a service, outcome, or problem scores high either way. A borderline message, arguably decidable, arguably too vague, scores low.

### When the underlying field can't be evaluated at all

A deterministic override, not left to the Judge's discretion, decided now rather than discovered as inconsistent behavior during M5, since it lands most often on exactly the rows likely to be seeded traps. If Section 5's ESCALATE bullet 1 fires for the field(s) behind a given criterion (missing, malformed, or unparseable, so the criterion can't be evaluated at all, not just that it fails), the corresponding Judge-scored sub-score is overridden to a fixed value after the Judge call, regardless of what the Judge actually returned.

For `budget_signal` this is a single-field question: `monthly_budget_usd` doesn't parse. Unlike the text fields below, blank/missing and malformed aren't split into separate cases here, an empty field and a garbled non-numeric one are equally unusable for a plausibility read, so both collapse into the one "unparseable" trigger: there's no data to have a plausibility read about either way. `need_clarity` is the same shape as `identity_verifiability`, missing and malformed are both possible and are handled below, not just missing.

`identity_verifiability` draws on three fields, matching Section 5's own scope note exactly (`email`, `website`, `company`).

**Vocabulary note:** Section 5 uses three terms for field problems, `missing`, `malformed`, `unparseable`. This section's language maps onto those directly rather than introducing a second vocabulary: `blank` below means missing. `Unusable`, `garbled`, `not email-shaped`, `corrupted`, and `unreadable` all mean malformed, present but not matching the expected shape for that field. `Unparseable` is used exactly as Section 5 uses it, reserved below for `monthly_budget_usd`, the one field here with a strict numeric shape. M2's Validate-stage checks should implement these three categories per field, not a separate vocabulary per section.

Blank is not treated the same as malformed, and the three identity fields aren't treated identically:

- **`email` blank or malformed** (garbled, not email-shaped): triggers the override. Email is the field criterion 1's test is actually built on ("email's domain is not a personal or free consumer provider..."); without a readable email there's no domain to classify as personal or company at all, not even the unverifiable case, there's nothing to classify.
- **`company` blank or malformed**: triggers the override. Section 5's "unverifiable" outcome describes a plausible-sounding company name as part of the typical case; when `company` is blank there's no name to weigh as plausible or not, so there's nothing to have a calibrated confidence read about, even though the Judge still makes its best decision-level call on the row using whatever else is available. Same reasoning as email; this is a statement about the confidence sub-score specifically, not the decision, which the Judge still makes either way.
- **`website` malformed**: triggers the override, present but unreadable (garbled encoding, control characters, content that plainly isn't a URL) isn't something to form a judgment about.
- **`website` blank**: does **not** trigger the override. This is the ordinary, expected shape of the "unverifiable" outcome Section 5 criterion 1 already defines (personal email, no website, a plausible-sounding company name), and the Judge scores `identity_verifiability` genuinely there: how confident it is in calling this row unverifiable rather than verifiable or fabricated. A blank website the Judge is meant to weigh (could be a real freelancer without a site, could be nothing) is a different case from a field that's actually unreadable, or a company claim that isn't there at all to weigh, and this pipeline keeps all three distinct rather than flattening them into the same automated 0.0.

`need_clarity` draws on one field, `message`, but like identity, blank and malformed aren't the same:

- **`message` missing or blank**: triggers the override. Nothing to read at all.
- **`message` malformed**: garbled or corrupted encoding, binary noise, content that isn't legible natural-language text at all. Triggers the override too, same reasoning as the identity fields: unreadable data isn't something to form a judgment about.
- **`message` present, legible, but vague or terse** (e.g. "let's talk," a single word, no stated ask): does **not** trigger the override. This is exactly Section 5 criterion 3's normal fail case, the message can be read, it just doesn't decide anything, and the Judge scores `need_clarity` genuinely there: how confident it is that the ask really is too vague to act on, versus borderline-decidable. Malformed and vague are different failure modes, one is a data problem, the other is a content judgment, and this pipeline keeps them distinct rather than treating every low-clarity message as a data gap.

Override values, standardized:

- `email` blank or malformed: `identity_verifiability` = 0.0, reason "cannot assess: email missing or unreadable"
- `company` blank or malformed: `identity_verifiability` = 0.0, reason "cannot assess: company missing or unreadable"
- `website` malformed (blank does not trigger this): `identity_verifiability` = 0.0, reason "cannot assess: website unreadable"
- `monthly_budget_usd` unparseable, blank/missing or malformed alike, one case, not two: `budget_signal` = 0.0, reason "cannot assess: monthly_budget_usd missing or malformed"
- `message` missing or malformed (garbled or unreadable, not simply vague or terse): `need_clarity` = 0.0, reason "cannot assess: message missing or unreadable"

The Judge is still asked for all three sub-scores on every row, per the Pipeline rule in Section 1, and whatever it actually returns stays in `llm_call`'s raw response untouched, that's the honest record of what the model said. The value that feeds the Section 6 aggregation below is the overridden one. Reasoning: once the input is gone or unreadable, there's nothing left to have a confidence-in-a-judgment-call about, that's a data-availability fact, not a judgment, the same distinction this section's opening paragraph already draws between the three Judge-scored signals and the two deterministic ones. Without this override, a row missing its budget field entirely could still get a model-guessed `budget_signal` from general disposition alone, indistinguishable in the log from a genuine plausibility read on real data. Forcing 0.0 with a standard reason keeps the two cases visibly different, and keeps every such row consistent with every other rather than depending on the model noticing and self-reporting correctly every time.

### The two deterministic sub-scores

Neither is asked of the Judge. Both are computed in Guardrails (M6) from flags Validate and Sanitize already produced upstream, using the formulas below. **[Assumed], PROVISIONAL**, same status as the $2000 budget threshold in Section 5: reasonable starting formulas, not derived from the real fixture, open to revision after the manual data pass.

4. **`data_completeness`.**
   Formula: 1 minus (count of incomplete fields, among the five that feed Section 5 criteria 1 to 3, `email`, `website`, `company`, `monthly_budget_usd`, `message`) divided by 5. All five complete: 1.0. Two of the five incomplete: 0.6. Pulls directly from Validate-stage output, no new detection logic, just a count.

   **Decided explicitly, not left ambiguous:** "incomplete" means malformed (any of the five), or missing where missing actually blocks evaluation, which is every field except `website`. `website` blank does not count against this score. A blank website is the ordinary, evaluable shape of the "unverifiable" outcome (Section 5 criterion 1; Section 6, "When the underlying field can't be evaluated at all"), not a gap that blocks evaluation, the Judge scores `identity_verifiability` on it genuinely rather than getting the deterministic override. Counting it here anyway would penalize the same row twice for the same reason, once correctly, through a genuinely low or uncertain `identity_verifiability`, and again through a completeness metric whose whole job is to measure whether the row *can* be evaluated, which for a blank website it still can. This exemption applies to `website` specifically: `company` blank still counts, since Section 6 already treats a blank `company` as an evaluability blocker, not the ordinary shape of anything.

5. **`trust_risk`** (1 = fully trusted, 0 = maximally flagged).
   Formula, priority order, highest-severity flag present sets the score, flags don't stack additively:
   - Sanitize flagged injection or manipulation content: 0.2
   - else Sanitize flagged security-threat content (Section 5, ESCALATE): 0.3
   - else Sanitize flagged sensitive content only (PII, legal or compliance-flavored language): 0.6
   - no Sanitize flags: 1.0

   Injection scores lowest on purpose: it's the trap category the brief singles out for the most scrutiny (scoring_rubric.md: "reviewers check this row first"), so it caps confidence the hardest. Security-threat content ranks just above it: actively hostile content (phishing, malware, extortion, threats) sits closer in severity to an attack on the agent than to a merely-sensitive disclosure, but it isn't the specific trap category the brief names, so it doesn't get injection's floor. Sensitive content ranks highest of the three flagged tiers because it's a handling-care problem, not necessarily a bad-faith one: a legitimate lead can mention something sensitive without the row being any less real.

### Aggregation (Guardrails, M6)

Two steps, in order, not one blended average:

1. **Weighted average of the four non-`trust_risk` scores.** Weights equal, 0.25 each. **[Assumed], PROVISIONAL:** no data-driven basis yet for weighting one over another, revisit once the manual pass and a few real Judge runs give something to weight against.

   **Open question, same provisional status, not resolved here:** three of the four averaged scores (`identity_verifiability`, `budget_signal`, `need_clarity`) are the Judge's confidence in its own judgment calls; the fourth (`data_completeness`) is a mechanical field-count with no judgment in it at all. Equal-weighting a confidence-in-a-judgment against a plain completeness ratio is a real modeling choice, not an obviously correct one, worth revisiting once real Judge runs exist to weight against.

   **Second open question, same provisional status, not resolved here:** the fields that trigger a Judge-scored override to 0.0 above (`email`/`website`/`company` for identity, `monthly_budget_usd` for budget, `message` for need) are the same fields `data_completeness` counts against below. A single missing or unreadable field currently lowers both the relevant Judge-scored sub-score, to exactly 0.0, and `data_completeness`, by 1/5, so that gap is penalized twice going into the weighted average. Not resolved here; revisit once real runs exist to check whether the double-count actually distorts `final_confidence` in practice or just washes out under the `trust_risk` cap.

   **Third open question, same provisional status, not resolved here:** Section 5 has six ESCALATE triggers; `trust_risk` above only draws on three of them (sensitive content, security-threat content, injection). Missing or malformed fields are covered separately, via `data_completeness` and the per-sub-score overrides above. Three more triggers have no representation in any of the five confidence sub-scores at all: the field-conflict bullet (two fields well-formed individually but contradicting each other), the non-sales-content bullet (a genuine complaint or support request, not a data problem at all), and Duplicate rows' cross-row conflict case (two submissions for the same lead disagreeing with each other). A row escalating for any of these three reasons could still compute a high `final_confidence`, since none of the five sub-scores are built to detect them. Not resolved here; revisit alongside the other open questions once real runs exist.

   ```
   weighted_average = 0.25 * identity_verifiability
                     + 0.25 * budget_signal
                     + 0.25 * need_clarity
                     + 0.25 * data_completeness
   ```

2. **`trust_risk` as a hard cap on that average, not an input to it.**

   ```
   final_confidence = min(weighted_average, trust_risk)
   ```

   If `trust_risk` is low, `final_confidence` cannot be high regardless of how the other four scores read, the same way Guardrails can already override the decision itself for the same category of row (Section 5, ESCALATE, injection bullet). A row with a textbook-clear identity, budget, and ask, but flagged for injection content, still ships with capped confidence: the four averaged scores describe how legible the row is, `trust_risk` describes how much the row can be trusted at all, and legibility doesn't buy back trust.