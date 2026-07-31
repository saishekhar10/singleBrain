"""Lead Triage Agent, Single Grain challenge 012, brief version 2026-07.

M1: Ingest. Reads fixtures/inbound_leads.csv into rows and stops there.
Validating, sanitizing, deduping, and judging are later stages.
"""

import csv
import sys

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


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FIXTURE
    rows = ingest(path)
    print(f"ingested {len(rows)} rows from {path}")
    print(", ".join(row["lead_id"] for row in rows))
