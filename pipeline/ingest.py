"""M1: Ingest. Reads the lead CSV into rows and stops there.

One stage per module, wired together by triage.py, which stays the single
entry point. See SPEC.md Section 2 on why this is organization and not an
orchestration framework.
"""

import csv

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
