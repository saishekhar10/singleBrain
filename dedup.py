"""M4: Dedup. Links rows that share an email, on an exact normalized key.

Linking annotates a row and never removes one: duplicates do not collapse, and
every row still reaches the Judge. The five rules this implements are stated in
MILESTONES.md's M4 section.
"""

from constants import OK

def _match_key(raw, status):
    """The value two rows must share to be linked, or None for no key at all.

    Two rules, settled 2026-08-01, deliberately kept separate:

    Rule 1, normalization: strip() then lowercase, together, over the whole
    address rather than the domain alone.

    Rule 2, the data-quality gate: only an `ok` email participates in matching.
    A missing or malformed one returns None, and dedup() never groups on None,
    so an unusable value matches nothing, including another unusable value.
    Rule 1 decides what two usable addresses must look like to be the same;
    rule 2 decides which addresses are usable at all.
    """
    if status != OK:
        return None
    return raw.strip().lower()


def dedup(rows, validations):
    """Link rows that share an email. Mutates nothing, drops nothing.

    Returns one result per row, in file order, aligned with `rows`. Linking
    annotates a row and never removes one: duplicates do not collapse, and
    every row still reaches the Judge per the locked Pipeline rule.

    "Earlier" means first occurrence in file order (rule 3), never
    `submitted_at`. M2 declared that field unreliable for decisions and
    L-012's own value proves why, so it gets no role here either. Nothing in
    this function reads it.

    Links are symmetric (rule 4): the first occurrence carries links to the
    later rows just as they carry links back to it, so neither side of a pair
    reads it blind. In a group of three or more the links form a star centered
    on the first occurrence (rule 5): every later row links to that one row,
    not to each other, and not chained through the row before it.

    Each result carries both `linked_lead_ids` and `linked_rows`. The rows are
    full copies, not a curated subset of fields, so M5 can compare whatever it
    needs to; `dedup_stage_trace` is the thin view that goes to the log.
    """
    if len(rows) != len(validations):
        raise ValueError(
            f"dedup got {len(rows)} rows and {len(validations)} validations; "
            "they must be aligned, since a silent zip() truncation here would "
            "drop rows from the pipeline"
        )

    keys = [
        _match_key(row.get("email"), validation["fields"]["email"])
        for row, validation in zip(rows, validations)
    ]

    # key -> positions carrying it, in file order. None keys are excluded
    # here rather than filtered later: that is rule 2's "matches nothing,
    # including another None" made structural instead of conditional.
    groups = {}
    for position, key in enumerate(keys):
        if key is not None:
            groups.setdefault(key, []).append(position)

    results = []
    for position, key in enumerate(keys):
        members = groups.get(key, []) if key is not None else []
        is_duplicate = len(members) > 1
        if not is_duplicate:
            linked = []
        elif position == members[0]:
            linked = members[1:]          # first occurrence: every later row
        else:
            linked = [members[0]]         # later row: the first occurrence only

        results.append(
            {
                "match_key": key,
                "is_duplicate": is_duplicate,
                # The group's anchor, which is this row itself on a first
                # occurrence. Lets a caller ask `first_occurrence_lead_id ==
                # lead_id` rather than needing a separate flag.
                "first_occurrence_lead_id": (
                    rows[members[0]]["lead_id"] if is_duplicate else None
                ),
                "linked_lead_ids": [rows[p]["lead_id"] for p in linked],
                "linked_rows": [dict(rows[p]) for p in linked],
            }
        )

    return results


def dedup_stage_trace(result):
    """The thin view of one dedup result, for run_log.json's stage_trace.

    Everything except `linked_rows`. SPEC.md Section 1 wants stage_trace to
    record what Dedup found and against which lead_id; copying whole rows in
    there would duplicate the input record in the log without adding a fact.
    The full rows exist for M5's prompt, not for the trace.
    """
    return {key: value for key, value in result.items() if key != "linked_rows"}
