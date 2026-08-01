"""Lead Triage Agent, Single Grain challenge 012, brief version 2026-07.

The entry point. Each stage lives in its own module and this file wires them
together in order, which is what SPEC.md Section 2 means by plain functions
called in sequence: no framework, no orchestration library, no components
passing messages to each other.

    ingest.py     M1  read the CSV into rows
    validate.py   M2  classify fields, compute the email-domain signals
    sanitize.py   M3  detect injection / security-threat / sensitive content
    dedup.py      M4  link rows sharing an email
    constants.py      vocabulary shared across stages

Run it:  python3 triage.py [path-to-csv]
"""

import sys

from constants import OK
from dedup import dedup
from ingest import ingest
from sanitize import sanitize
from validate import DOMAIN_SIGNALS, validate

DEFAULT_FIXTURE = "fixtures/inbound_leads.csv"


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FIXTURE
    rows = ingest(path)
    print(f"ingested {len(rows)} rows from {path}")
    print(", ".join(row["lead_id"] for row in rows))
    print()
    validations = [validate(row) for row in rows]
    links = dedup(rows, validations)
    for row, result, link in zip(rows, validations, links):
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
        if link["linked_lead_ids"]:
            linked = "+".join(link["linked_lead_ids"])
        elif link["match_key"] is None:
            linked = "no key"
        else:
            linked = "none"
        print(
            f"{row['lead_id']}  {problems or 'all five ok'}"
            f"  budget={result['budget_value']}"
            f"  domain={domain}"
            f"  content={content}"
            f"  linked={linked}"
            f"{'' if result['submitted_at_valid'] else '  submitted_at=INVALID'}"
        )
