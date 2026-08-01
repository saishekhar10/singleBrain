"""M3: Sanitize. Detects content categories on a row and never mutates it.

The defense against injected instructions is M5's labeled data boundary, not
rewriting the input: rewriting it would corrupt the honest record run_log.json
exists to preserve. Detecting anything never skips the Judge.
"""

import re

from constants import CONTENT_CATEGORIES, INJECTION, SECURITY_THREAT, SENSITIVE_CONTENT

# Settled 2026-07-31: message is where this fixture's adversarial content sits,
# but M5's prompt carries name and company too, so all three are attack surface.
SCANNED_FIELDS = ("name", "company", "message")

# Most rules below require two things to co-occur inside one sentence. That is
# what separates pattern detection from keyword matching: "compliance" or
# "urgent" or "we spoke" alone say nothing, and MILESTONES.md's N1/N2/N3
# near-misses exist to fail any detector that forgets it.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|[\n\r]+")

# ---- injection ----
_OVERRIDE_VERB = re.compile(
    r"\b(?:ignore|disregard|forget|override|bypass|skip|discard)\b", re.I)
_INSTRUCTION_NOUN = re.compile(
    r"\b(?:instructions?|prompts?|rules?|directions?|guidelines?|"
    r"system\s+messages?)\b", re.I)
# The third signal that makes instruction_override mean something. Without it,
# "we need someone willing to ignore the usual rules of SEO" reads as an attack.
# Injection targets instructions the *reader* was given; a lead talking about
# rules in general is talking about its own industry.
_OVERRIDE_SCOPE = re.compile(
    r"\b(?:previous|prior|earlier|above|preceding|original|initial|system)\b"
    r"|\byour?\b", re.I)
# The four decision values this pipeline emits.
_DECISION_ENUM = re.compile(r"\b(?:qualify|nurture|reject|escalate)\b", re.I)
# Assigning a decision to *this submission*, not merely naming one. The
# self-reference is load-bearing: this pipeline triages marketing leads, and
# "help us score and qualify inbound leads" is ordinary prospect vocabulary,
# while "mark this as QUALIFY" is not something a real lead ever writes.
_ASSIGNS_OWN_DECISION = re.compile(
    r"\b(?:classify|mark|record|label|set|score|rate|treat|flag|"
    r"categor(?:ize|ise))\b[^.!?]{0,40}\b(?:this|my)\b[^.!?]{0,40}"
    r"\bas\b\s+(?:a\s+)?(?:qualify|nurture|reject|escalate)\b", re.I)
# Confidence supplied as a *parameter*, which the "with/at/to" prefix marks.
# "We have full confidence in your team" is a sentiment and stays clean.
_CONFIDENCE_PARAMETER = re.compile(
    r"\b(?:with|at|to)\s+(?:a\s+)?(?:confidence\s+(?:of\s+)?"
    r"(?:1(?:\.0+)?|0\.\d+)|(?:full|maximum|highest|total)\s+confidence)\b", re.I)
_SELF_REFERENCE = re.compile(r"\b(?:this|my)\b", re.I)
_AGENT_ADDRESS = re.compile(
    r"\byou\s+are\s+(?:an?\s+)?(?:ai|llm|language\s+model|assistant|bot|agent)\b"
    r"|\b(?:your|the)\s+system\s+(?:prompt|message)\b"
    r"|\bact\s+as\s+(?:an?\s+)?(?:ai|assistant|admin|administrator)\b"
    r"|\bdeveloper\s+mode\b", re.I)

# ---- security threat ----
# Executable and script payloads only. Deliberately excludes .com and .zip:
# both are ordinary TLDs, and matching them would fire on half the fixture.
_EXECUTABLE_LINK = re.compile(
    r"https?://\S+\.(?:exe|scr|bat|cmd|pif|msi|jar|vbs|ps1|apk|dmg|iso|hta)\b", re.I)
_EXECUTABLE_ATTACHMENT = re.compile(
    r"\b(?:attach(?:ed|ment)s?|download)\b[^.!?]{0,80}"
    r"\.(?:exe|scr|bat|cmd|pif|msi|jar|vbs|ps1|apk|dmg|iso|hta)\b", re.I)
# Assets are nouns and demands are verbs, kept strictly disjoint. "wire" was
# briefly in both, which would have let one token satisfy an asset-plus-verb
# pair on its own, the same double-duty defect as overdue/urgency and
# invoice/asset below it.
_SENSITIVE_ASSET = re.compile(
    r"\b(?:billing|payments?|invoices?|cards?|bank|accounts?|credentials?|"
    r"passwords?|logins?|funds|ach|routing)\b", re.I)
_DEMAND_VERB = re.compile(
    r"\b(?:re-?confirm|confirm|verify|validate|update|provide|send|settle|"
    r"pay|remit|wire|transfer|enter|submit|reply\s+with)\b", re.I)
# Time pressure only. Two things are deliberately absent. A bare "now", because
# N2's "now that our Q4 budget is approved" is an ordinary returning customer.
# And "overdue"/"past due", because those are obligation markers listed under
# _OBLIGATION below: leaving them here too let one word satisfy both halves of
# the co-occurrence rule that pairs them, which collapses that rule back into
# the keyword matching it exists to avoid. Caught by
# test_pretext_sentence_alone_does_not_fire.
_URGENCY = re.compile(
    r"\b(?:today|immediately|right\s+away|at\s+once|asap|urgent(?:ly)?|"
    r"within\s+\d+\s*(?:hours?|days?)|by\s+end\s+of\s+day)\b"
    r"|\bto\s+avoid\b[^.!?]{0,40}\b(?:interruption|suspension|cancellation|"
    r"termination|late\s+fees?)\b"
    r"|\b(?:will\s+be|be)\s+(?:cancelled|canceled|suspended|terminated|closed)\b"
    r"|\bor\s+the\s+\w+\s+lapses\b", re.I)
# An asserted prior relationship or outstanding obligation. On its own this is
# just a returning customer; it only means anything paired with a demand.
_PRIOR_RELATIONSHIP = re.compile(
    r"\bwe\s+spoke\b|\bas\s+(?:we\s+)?discussed\b"
    r"|\bper\s+(?:our|the)\s+(?:call|conversation|agreement|contract)\b"
    r"|\bthe\s+(?:agreement|contract)\s+we\s+signed\b"
    r"|\bfollowing\s+up\s+on\s+(?:the|our|your)\s+"
    r"(?:invoice|balance|payment|account)\b", re.I)
_OBLIGATION = re.compile(
    r"\b(?:overdue|past\s+due|unpaid|outstanding\s+(?:balance|invoice|amount)|"
    r"remaining\s+balance|balance\s+due|amount\s+due)\b", re.I)
_EXTORTION = re.compile(
    r"\bunless\s+you\s+pay\b"
    r"|\bor\s+we\s+will\s+(?:publish|release|leak|expose|report)\b"
    r"|\bwe\s+have\s+(?:copies\s+of|access\s+to)\b", re.I)

# ---- sensitive content ----
_PERSONAL_DATA = re.compile(
    r"\bpersonal\s+(?:data|information|details)\b|\bpii\b"
    r"|\bdata\s+you\s+(?:hold|have|store|collected)\b"
    r"|\bmy\s+(?:data|information)\b", re.I)
_DATA_REQUEST_VERB = re.compile(
    r"\b(?:delete|erase|remove|disclose|rectify|restrict|export|"
    r"opt[\s-]?out)\b", re.I)
# "subject access request" is deliberately not here: it contains the word
# "request", so it satisfied _REQUEST_VERB on its own and made the citation
# rule fire on one phrase, the same double-duty defect as overdue/urgency. It
# has its own rule below. "section N" is gone for a different reason: RFPs and
# creative briefs are full of numbered sections, and this pipeline reads
# marketing leads. "article N" stays, being rare in ordinary business prose.
_LEGAL_CITATION = re.compile(
    r"\b(?:gdpr|ccpa|cpra|hipaa|coppa|pipeda|lgpd)\b"
    r"|\barticle\s+\d+\b", re.I)
# A subject access request being *made of us*, not a vendor describing the SAR
# tooling they sell. Decision 1's boundary, applied to the one phrase that
# names the request type outright.
_SAR_FILED = re.compile(
    r"\b(?:submit(?:ting|ted)?|fil(?:e|ing|ed)|mak(?:e|ing)|lodg(?:e|ing|ed)|"
    r"hereby|sending)\b[^.!?]{0,30}\bsubject\s+access\s+request\b", re.I)
# The request has to be about data we hold on them. Without this, a lead
# describing its own data hygiene ("remove personal data from our old funnel
# exports") reads as a data-subject request against us.
_DIRECTED_AT_US = re.compile(
    r"\b(?:you|your)\b[^.!?]{0,25}\b(?:hold|have|store[ds]?|collect(?:ed)?|"
    r"keep|kept|retain(?:ed)?|process(?:ed)?)\b"
    r"|\babout\s+(?:me|us|my)\b", re.I)
_REQUEST_VERB = re.compile(
    r"\b(?:request(?:ing|ed)?|demand(?:ing|ed)?|require|insist)\b", re.I)
# A lead describing its own legal review is not this. "our lawyers" pointed at
# us is; "our own legal team signs off on ad copy" is not.
_LEGAL_ACTION_THREAT = re.compile(
    r"\blegal\s+action\b|\bcease\s+and\s+desist\b"
    r"|\bfile\s+a\s+(?:complaint|claim|suit)\b"
    r"|\breport\s+(?:you|this)\s+to\s+the\b"
    r"|\bhear\s+from\s+(?:our|my)\s+(?:lawyers?|attorneys?|counsel)\b", re.I)


def _sentences(text):
    return [part for part in _SENTENCE_SPLIT.split(text) if part.strip()]


def detect_injection(text):
    """Rule names that fired, empty if none. Content aimed at the agent itself."""
    fired = []
    for sentence in _sentences(text):
        if (_OVERRIDE_VERB.search(sentence)
                and _INSTRUCTION_NOUN.search(sentence)
                and _OVERRIDE_SCOPE.search(sentence)):
            fired.append("instruction_override")
        if _ASSIGNS_OWN_DECISION.search(sentence):
            fired.append("assigns_its_own_decision")
        if (_CONFIDENCE_PARAMETER.search(sentence)
                and _DECISION_ENUM.search(sentence)
                and _SELF_REFERENCE.search(sentence)):
            fired.append("pins_its_own_confidence")
        if _AGENT_ADDRESS.search(sentence):
            fired.append("addressed_to_the_agent")
    return sorted(set(fired))


def detect_security_threat(text):
    """Rule names that fired, empty if none. Content aimed at the business."""
    fired = []
    if _EXECUTABLE_LINK.search(text) or _EXECUTABLE_ATTACHMENT.search(text):
        fired.append("executable_payload")
    if _EXTORTION.search(text):
        fired.append("extortion")
    for sentence in _sentences(text):
        if (_SENSITIVE_ASSET.search(sentence)
                and _DEMAND_VERB.search(sentence)
                and _URGENCY.search(sentence)):
            fired.append("credential_or_payment_pressure")

    # Pattern (a), the one rule here that spans the whole message rather than a
    # sentence: pretext is a two-part structure by nature, the claim in one
    # sentence and the demand in the next, which is exactly how L-020 is built.
    # Whether the claimed relationship is *false* is not knowable from the row,
    # so this never fires on the claim alone. See CLAUDE.md's documented design
    # decisions and MILESTONES.md's M3 judgment-vs-pattern note.
    #
    # The claim and the payment demand must come from *different sentences*.
    # Without that, one noun does double duty: "outstanding invoice" supplies
    # the obligation claim, and "invoice" is a _SENSITIVE_ASSET too, so an
    # ordinary "please send me the outstanding invoice" was left needing only a
    # common verb to read as a threat. Same defect class as the overdue/urgency
    # overlap above, one level deeper. Urgency and executable payloads stay
    # message-level: their vocabulary shares nothing with the claim's, so they
    # cannot double up.
    claim_sentences = []
    demand_sentences = []
    for sentence in _sentences(text):
        if _PRIOR_RELATIONSHIP.search(sentence) or _OBLIGATION.search(sentence):
            claim_sentences.append(sentence)
        elif _SENSITIVE_ASSET.search(sentence) and _DEMAND_VERB.search(sentence):
            demand_sentences.append(sentence)

    claims_relationship = bool(claim_sentences)
    demands_something = bool(
        _EXECUTABLE_LINK.search(text)
        or _EXECUTABLE_ATTACHMENT.search(text)
        or _URGENCY.search(text)
        or demand_sentences
    )
    if claims_relationship and demands_something:
        fired.append("pretext_obligation_with_demand")
    return sorted(set(fired))


def detect_sensitive_content(text):
    """Rule names that fired, empty if none.

    Settled 2026-07-31: a business describing its own regulatory context does
    not fire; a legal or compliance demand directed at us does. Every rule below
    therefore needs a request or a citation pointed at this business, never the
    mere presence of compliance vocabulary.
    """
    fired = []
    for sentence in _sentences(text):
        if (_DATA_REQUEST_VERB.search(sentence)
                and _PERSONAL_DATA.search(sentence)
                and _DIRECTED_AT_US.search(sentence)):
            fired.append("data_subject_request")
        if _LEGAL_CITATION.search(sentence) and (
                _REQUEST_VERB.search(sentence) or _DATA_REQUEST_VERB.search(sentence)):
            fired.append("legal_citation_with_demand")
        if _SAR_FILED.search(sentence):
            fired.append("subject_access_request")
        if _LEGAL_ACTION_THREAT.search(sentence):
            fired.append("threat_of_legal_action")
    return sorted(set(fired))


_DETECTORS = (
    (INJECTION, detect_injection),
    (SECURITY_THREAT, detect_security_threat),
    (SENSITIVE_CONTENT, detect_sensitive_content),
)


def sanitize(row):
    """Detect content categories on one row. Mutates nothing, drops nothing.

    Returns SPEC.md Section 1's content_flags: a list of {category,
    description}, empty when nothing fired, one entry per category detected.

    All three detectors run on every scanned field of every row. There is no
    priority order and no short-circuit here: SPEC.md Section 1 allows more than
    one category on the same row and says this field records everything found,
    so a row carrying two kinds of hostile content reports both. Detecting
    anything never skips the Judge, per the locked Pipeline rule.
    """
    hits = {category: [] for category, _ in _DETECTORS}
    for field in SCANNED_FIELDS:
        value = row.get(field) or ""
        for category, detector in _DETECTORS:
            for rule in detector(value):
                hits[category].append(f"{field}:{rule}")

    return [
        {
            "category": category,
            "description": "matched " + ", ".join(hits[category]),
        }
        for category in CONTENT_CATEGORIES
        if hits[category]
    ]
