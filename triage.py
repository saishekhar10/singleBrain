"""Lead Triage Agent, Single Grain challenge 012, brief version 2026-07.

M1: Ingest. Reads fixtures/inbound_leads.csv into rows and stops there.
M2: Validate. Classifies the five criteria-feeding fields and computes the one
deterministic identity signal SPEC.md Section 5 assigns to a pre-Judge stage.

Sanitizing, deduping, and judging are later stages.
"""

import csv
import re
import sys
import unicodedata
from datetime import datetime

# SPEC.md Section 1's input schema, in order.
SCHEMA = (
    "lead_id",
    "submitted_at",
    "name",
    "email",
    "company",
    "website",
    "monthly_budget_usd",
    "message",
    "source",
)

# Where csv.DictReader parks cells past the last schema column. A row this key
# shows up on is ragged, which is M2's problem to classify, not a reason for
# Ingest to drop it.
EXTRA_FIELDS_KEY = "_extra_fields"

DEFAULT_FIXTURE = "fixtures/inbound_leads.csv"

# The three email-domain signals validate() reports, in output order. Used by
# the smoke run below and by M5 later, so the names live in one place.
DOMAIN_SIGNALS = (
    "email_domain_is_personal_provider",
    "is_disposable_email_domain",
    "is_reserved_or_example_domain",
)


def ingest(path):
    """Read the fixture into a list of raw-string dicts, in file order.

    No row is dropped, reordered, or mutated. Blank fields, unparseable
    budgets, invalid timestamps, and duplicate emails all pass through
    untouched, because deciding what any of that means belongs to the stages
    downstream of this one.

    Raises ValueError only when the header does not match SCHEMA, which is a
    file-contract violation rather than a row-level problem.
    """
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, restkey=EXTRA_FIELDS_KEY, restval=None)
        if reader.fieldnames != list(SCHEMA):
            raise ValueError(
                "header does not match SCHEMA\n"
                f"  expected: {list(SCHEMA)}\n"
                f"  found:    {reader.fieldnames}"
            )
        return [dict(row) for row in reader]


# --------------------------------------------------------------------- M2

# SPEC.md Section 6's vocabulary note: three terms for field problems, plus OK.
# M6 reads these same words back off Validate's output, so they are defined
# once here rather than restated per stage.
OK = "ok"
MISSING = "missing"
MALFORMED = "malformed"
UNPARSEABLE = "unparseable"

# The five fields that feed Section 5's criteria 1 to 3, per its scope note.
# submitted_at is deliberately not here: it is checked for crash-safety only
# and never enters this vocabulary, however broken it is.
CRITERIA_FIELDS = (
    "email",
    "website",
    "company",
    "monthly_budget_usd",
    "message",
)

# Three separate email-domain signals follow, deliberately not merged into one
# "bad domain" flag. SPEC.md Section 5's design note puts all of them here:
# classifying a domain is pattern detection, not judgment, so it stays in plain
# Python and each resulting signal is handed to the Judge as its own fact. The
# Judge weighs them; it never pattern-matches domains itself.
#
# They stay distinct because they mean different things under Section 5
# criterion 1's unverifiable-versus-fabricated split. Consumer webmail says a
# real person has no company domain to offer. A disposable inbox says someone
# is deliberately avoiding contact. A reserved or example domain says the value
# is placeholder text and no one is behind it at all. Collapsing them would
# hand the Judge a flag it cannot act on.

# Personal / free consumer webmail. Consumer mailboxes only, not the two
# categories below.
PERSONAL_EMAIL_DOMAINS = frozenset({
    "aol.com",
    "fastmail.com",
    "gmail.com",
    "gmx.com",
    "gmx.net",
    "googlemail.com",
    "hey.com",
    "hotmail.co.uk",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "mac.com",
    "mail.com",
    "me.com",
    "msn.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "tutanota.com",
    "yahoo.co.uk",
    "yahoo.com",
    "yandex.com",
    "ymail.com",
    "zoho.com",
})

# Throwaway / temporary inbox services. Distinct from consumer webmail above:
# a gmail.com address is someone's real mailbox, a mailinator.com address is a
# public one anyone can read and no one owns.
DISPOSABLE_EMAIL_DOMAINS = frozenset({
    "10minutemail.com",
    "discard.email",
    "dispostable.com",
    "emailondeck.com",
    "fakeinbox.com",
    "getnada.com",
    "grr.la",
    "guerrillamail.com",
    "guerrillamail.net",
    "mailcatch.com",
    "maildrop.cc",
    "mailinator.com",
    "mailinator.net",
    "mailnesia.com",
    "mintemail.com",
    "mohmal.com",
    "sharklasers.com",
    "spam4.me",
    "spamgourmet.com",
    "temp-mail.org",
    "tempinbox.com",
    "tempmail.com",
    "throwawaymail.com",
    "trashmail.com",
    "yopmail.com",
})

# Reserved for documentation and testing, so no real party is behind them.
# RFC 6761 special-use TLDs, plus .local from RFC 6762's mDNS reservation.
RESERVED_TLDS = frozenset({"example", "invalid", "local", "localhost", "test"})

# Exactly one @, with a non-empty local part and a non-empty domain part.
# Both sides exclude @ and whitespace, so a second @ fails the match outright.
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+$")

_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")

# Optional sign, optional $, digits with well-formed thousands grouping or no
# grouping at all, optional single decimal point, optional k/K meaning x1000.
# Settled 2026-07-31: k/K is the only accepted suffix. m/M is unparseable.
_BUDGET_SHAPE = re.compile(
    r"""^
    (?P<sign>[-+])?
    \$?
    (?P<digits>\d{1,3}(?:,\d{3})*|\d+)
    (?:\.(?P<frac>\d+))?
    (?P<thousands>[kK])?
    $""",
    re.VERBOSE,
)


def _is_blank(raw):
    """True for absent, empty, and whitespace-only cells alike.

    None shows up on a short ragged row, where csv.DictReader fills absent
    columns with restval. Signed off 2026-07-31: a cell of spaces is not a
    value, and calling it missing is a shape call, not a judgment call.
    """
    return raw is None or raw.strip() == ""


def _is_illegible(text):
    """True when the text is not legible as text at all.

    This is the whole of what "malformed" means for the free-text fields,
    settled 2026-07-31: control characters or a U+FFFD left behind by a failed
    decode. Vague, terse, meaningless, and HTML-wrapped are all legible, so
    none of them land here; whether they say anything useful is the Judge's
    question in M5, not a data-shape question for this stage.
    """
    return any(
        char == "�"
        or (unicodedata.category(char) == "Cc" and char not in "\t\n\r")
        for char in text
    )


def validate_email(raw):
    """missing / malformed / ok. Shape only, never plausibility."""
    if _is_blank(raw):
        return MISSING
    value = raw.strip()
    if _is_illegible(value) or not _EMAIL_SHAPE.match(value):
        return MALFORMED
    labels = value.rsplit("@", 1)[1].split(".")
    # A domain needs at least one dot and no empty labels: a@b and a@b..c fail.
    if len(labels) < 2 or not all(labels):
        return MALFORMED
    return OK


def validate_website(raw):
    """missing / malformed / ok. A missing scheme is not a defect."""
    if _is_blank(raw):
        return MISSING
    value = raw.strip()
    if _is_illegible(value) or re.search(r"\s", value):
        return MALFORMED
    host = _URL_SCHEME.sub("", value, count=1)
    host = re.split(r"[/?#]", host, maxsplit=1)[0]
    host = host.rsplit("@", 1)[-1].split(":", 1)[0]
    labels = host.split(".")
    if len(labels) < 2 or not all(labels):
        return MALFORMED
    return OK


def validate_company(raw):
    """missing / malformed / ok. "Implausible" is not malformed."""
    if _is_blank(raw):
        return MISSING
    return MALFORMED if _is_illegible(raw) else OK


def validate_message(raw):
    """missing / malformed / ok. "Vague" is not malformed."""
    if _is_blank(raw):
        return MISSING
    return MALFORMED if _is_illegible(raw) else OK


def validate_budget(raw):
    """Return (status, value). Value is None unless the status is OK.

    Blank returns MISSING and present-but-non-numeric returns UNPARSEABLE,
    kept distinct here on purpose. SPEC.md Section 6 collapses the two into a
    single budget_signal override trigger, and M6 is where that collapse
    happens; discarding the distinction this early would lose information for
    no gain.
    """
    if _is_blank(raw):
        return MISSING, None
    match = _BUDGET_SHAPE.match(raw.strip())
    if match is None:
        return UNPARSEABLE, None
    digits = match.group("digits").replace(",", "")
    frac = match.group("frac")
    value = float(f"{digits}.{frac}") if frac else float(digits)
    if match.group("thousands"):
        value *= 1000
    if match.group("sign") == "-":
        value = -value
    return OK, value


def _email_domain(raw, status):
    """The email's lowercased domain, or None when there is none to read.

    None is the shared "nothing to classify" case for all three signals below.
    It is not the same as a negative result: None means the email is missing or
    malformed so no domain was ever examined, while False asserts a domain was
    read and did not match. SPEC.md Section 6 already treats "nothing to
    classify" as its own case, so the signals keep it rather than flattening it.
    """
    if status != OK:
        return None
    return raw.strip().rsplit("@", 1)[1].lower()


def email_domain_is_personal_provider(raw, status):
    """True / False / None. Consumer webmail only."""
    domain = _email_domain(raw, status)
    return None if domain is None else domain in PERSONAL_EMAIL_DOMAINS


def is_disposable_email_domain(raw, status):
    """True / False / None. Throwaway inbox services only."""
    domain = _email_domain(raw, status)
    return None if domain is None else domain in DISPOSABLE_EMAIL_DOMAINS


def is_reserved_or_example_domain(raw, status):
    """True / False / None. Documentation and testing placeholders.

    Two rules, because one is not enough. RFC 6761's special-use TLDs cover
    anything.test and anything.invalid, but RFC 2606 reserves only the three
    literal names example.com, example.net, and example.org, so a placeholder
    under a country-code TLD (example.de, as on L-019) is not reserved by any
    RFC. It follows the same convention, though, so the second rule catches a
    two-label domain whose first label is "example", which covers RFC 2606's
    three literals as a side effect and needs no separate list.

    Held to exactly two labels on purpose: example.mycompany.com is a real
    subdomain of a real company, not a placeholder, and telling the two apart
    in general needs a public suffix list, which is far more than 20 rows
    justify. The known gap is a placeholder under a multi-part suffix
    (example.co.uk), which this returns False for.
    """
    domain = _email_domain(raw, status)
    if domain is None:
        return None
    labels = domain.split(".")
    return labels[-1] in RESERVED_TLDS or (len(labels) == 2 and labels[0] == "example")


def check_submitted_at(raw):
    """Parse for crash-safety only. Never raises.

    Returns a datetime, or None when the value is absent or not a real
    timestamp. Per SPEC.md Section 5's scope note this field never feeds the
    five-field missing/malformed vocabulary, so a broken value here annotates
    the row and changes nothing else.
    """
    if _is_blank(raw):
        return None
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def validate(row):
    """Classify one ingested row. Mutates nothing, drops nothing.

    Returns a separate result dict and leaves the row exactly as ingest()
    produced it. Every row is classified and passed on: per SPEC.md Section 1's
    locked Pipeline rule, no deterministic stage may skip a row past the Judge,
    whatever it finds here.
    """
    budget_status, budget_value = validate_budget(row.get("monthly_budget_usd"))
    email_status = validate_email(row.get("email"))
    fields = {
        "email": email_status,
        "website": validate_website(row.get("website")),
        "company": validate_company(row.get("company")),
        "monthly_budget_usd": budget_status,
        "message": validate_message(row.get("message")),
    }
    email_raw = row.get("email")
    return {
        "fields": fields,
        "budget_value": budget_value,
        # Three independent facts about the email domain, not one merged flag.
        # Each is True / False / None; see _email_domain on why None is kept.
        "email_domain_is_personal_provider": email_domain_is_personal_provider(
            email_raw, email_status
        ),
        "is_disposable_email_domain": is_disposable_email_domain(
            email_raw, email_status
        ),
        "is_reserved_or_example_domain": is_reserved_or_example_domain(
            email_raw, email_status
        ),
        "submitted_at_valid": check_submitted_at(row.get("submitted_at")) is not None,
        # None on a well-shaped row. Non-None means the CSV row carried more
        # cells than the schema has columns, which M1 deliberately left for
        # this stage to classify.
        "extra_fields": row.get(EXTRA_FIELDS_KEY),
    }


# --------------------------------------------------------------------- M3

# SPEC.md Section 1's content_flags categories, matching Section 6's trust_risk
# names exactly. Priority among them lives in M6's trust_risk formula and
# nowhere in this stage: here all three are checked independently and every one
# that fires is recorded, because SPEC.md Section 1 says content_flags records
# everything Sanitize found, not just the one driving the score.
INJECTION = "injection"
SECURITY_THREAT = "security_threat"
SENSITIVE_CONTENT = "sensitive_content"

CONTENT_CATEGORIES = (INJECTION, SECURITY_THREAT, SENSITIVE_CONTENT)

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


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FIXTURE
    rows = ingest(path)
    print(f"ingested {len(rows)} rows from {path}")
    print(", ".join(row["lead_id"] for row in rows))
    print()
    for row in rows:
        result = validate(row)
        problems = {
            field: status
            for field, status in result["fields"].items()
            if status != OK
        }
        fired = [name for name in DOMAIN_SIGNALS if result[name]]
        if result["email_domain_is_personal_provider"] is None:
            domain = "no domain to classify"
        else:
            # "unflagged" rather than "company domain": none of the three
            # signals fired, which is not the same as having verified anything.
            domain = "+".join(fired) if fired else "unflagged"
        flags = sanitize(row)
        content = "+".join(flag["category"] for flag in flags) if flags else "clean"
        print(
            f"{row['lead_id']}  {problems or 'all five ok'}"
            f"  budget={result['budget_value']}"
            f"  domain={domain}"
            f"  content={content}"
            f"{'' if result['submitted_at_valid'] else '  submitted_at=INVALID'}"
        )
