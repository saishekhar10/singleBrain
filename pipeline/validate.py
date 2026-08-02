"""M2: Validate. Classifies the five criteria-feeding fields and computes the
three deterministic email-domain signals SPEC.md Section 5 assigns to a
pre-Judge stage.

Mutates nothing and drops nothing: every row is classified and passed on, per
SPEC.md Section 1's locked Pipeline rule.
"""

import re
import unicodedata
from datetime import datetime

from pipeline.constants import MALFORMED, MISSING, OK, UNPARSEABLE
from pipeline.ingest import EXTRA_FIELDS_KEY

# The three email-domain signals validate() reports, in output order. Used by
# the smoke run in triage.py and by M5 later, so the names live in one place.
DOMAIN_SIGNALS = (
    "email_domain_is_personal_provider",
    "is_disposable_email_domain",
    "is_reserved_or_example_domain",
)

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
