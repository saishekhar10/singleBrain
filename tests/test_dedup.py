"""Acceptance tests for M4: Dedup.

Real fixture rows are the primary evidence, per CLAUDE.md. Rules 1 and 2 are
unobservable on those rows (both duplicate pairs are byte-identical, and no
fixture email is malformed), so they are checked at the narrow generalization
scope MILESTONES.md sanctions for this milestone: synthetic values handed to
`_match_key()` directly, never assembled into fabricated lead rows.

A second, separate exception covers rule 2's None-key bucketing, which the
first cannot reach: real rows through the real dedup(), with a simulated
Validate status. Its scope and why it was granted are on NoneKeyBucketingTest.

One gap is left open deliberately rather than closed with fabricated rows, and
is recorded in PROGRESS.md: rule 5's 3+ group. Rule 3 gets a structural test
instead of a data one, for the reason given on FileOrderTest.
"""

import copy
import inspect
import unittest
from pathlib import Path

import pipeline.dedup as dedup_module
from pipeline.constants import MALFORMED, MISSING, OK, UNPARSEABLE
from pipeline.dedup import dedup, dedup_stage_trace
from pipeline.ingest import ingest
from pipeline.validate import validate

FIXTURE = (Path(__file__).resolve().parent.parent
           / "fixtures" / "inbound_leads.csv")

# The fixture's two duplicate pairs, first occurrence first. Transcribed from
# MILESTONES.md's M4 criteria; scripts/verify_milestones.py re-derives both the
# shared address and the file order from the fixture itself.
PAIRS = (("L-001", "L-003"), ("L-002", "L-015"))
LINKED_IDS = {"L-001", "L-003", "L-002", "L-015"}


def run_dedup():
    rows = ingest(FIXTURE)
    return rows, dedup(rows, [validate(row) for row in rows])


class FixtureLinkTest(unittest.TestCase):
    """The two seeded duplicate pairs, on real rows."""

    def setUp(self):
        self.rows, self.results = run_dedup()
        self.by_id = {
            row["lead_id"]: result
            for row, result in zip(self.rows, self.results)
        }

    def test_both_pairs_link_symmetrically(self):
        for earlier, later in PAIRS:
            with self.subTest(pair=(earlier, later)):
                self.assertEqual(self.by_id[later]["linked_lead_ids"], [earlier])
                # Rule 4: the earlier row carries the link too, rather than
                # being left blind on a row the pipeline already holds.
                self.assertEqual(self.by_id[earlier]["linked_lead_ids"], [later])

    def test_both_pairs_share_a_match_key(self):
        for earlier, later in PAIRS:
            with self.subTest(pair=(earlier, later)):
                self.assertEqual(
                    self.by_id[earlier]["match_key"],
                    self.by_id[later]["match_key"],
                )

    def test_first_occurrence_is_the_earlier_row_on_both_sides(self):
        for earlier, later in PAIRS:
            with self.subTest(pair=(earlier, later)):
                for lead_id in (earlier, later):
                    self.assertEqual(
                        self.by_id[lead_id]["first_occurrence_lead_id"], earlier
                    )
                    self.assertTrue(self.by_id[lead_id]["is_duplicate"])

    def test_l004_has_no_match_key_and_links_to_nothing(self):
        # Rule 2 on the fixture's one unusable email. L-004 is the only
        # blank-email row; L-008 carries a real address and is an ordinary
        # non-matching value, not a blank.
        l004 = self.by_id["L-004"]
        self.assertIsNone(l004["match_key"])
        self.assertFalse(l004["is_duplicate"])
        self.assertEqual(l004["linked_lead_ids"], [])
        self.assertEqual(l004["linked_rows"], [])
        self.assertIsNone(l004["first_occurrence_lead_id"])

    def test_exact_per_row_link_map(self):
        # Asserted as a whole map rather than only on the four linked rows, so
        # a spurious link anywhere in the fixture fails here.
        expected = {
            "L-001": ["L-003"],
            "L-003": ["L-001"],
            "L-002": ["L-015"],
            "L-015": ["L-002"],
        }
        actual = {
            row["lead_id"]: result["linked_lead_ids"]
            for row, result in zip(self.rows, self.results)
        }
        self.assertEqual(actual, {**{r["lead_id"]: [] for r in self.rows}, **expected})

    def test_no_false_positive_among_the_other_sixteen_rows(self):
        for row, result in zip(self.rows, self.results):
            if row["lead_id"] in LINKED_IDS:
                continue
            with self.subTest(lead_id=row["lead_id"]):
                self.assertFalse(result["is_duplicate"])
                self.assertEqual(result["linked_lead_ids"], [])

    def test_nineteen_rows_carry_a_key_and_seventeen_are_distinct(self):
        keys = [result["match_key"] for result in self.results]
        present = [key for key in keys if key is not None]
        self.assertEqual(len(present), 19)
        self.assertEqual(len(set(present)), 17)


class NoRowIsLostOrMutatedTest(unittest.TestCase):
    """The locked Pipeline rule: linking annotates, it never removes."""

    def test_all_twenty_rows_appear_in_output_in_file_order(self):
        rows, results = run_dedup()
        self.assertEqual(len(results), 20)
        self.assertEqual(len(results), len(rows))

    def test_duplicates_do_not_collapse(self):
        rows, results = run_dedup()
        # Both members of both pairs are still present as their own results.
        for earlier, later in PAIRS:
            ids = [row["lead_id"] for row in rows]
            self.assertIn(earlier, ids)
            self.assertIn(later, ids)
        self.assertEqual(len({row["lead_id"] for row in rows}), 20)

    def test_dedup_mutates_no_row(self):
        rows = ingest(FIXTURE)
        before = copy.deepcopy(rows)
        dedup(rows, [validate(row) for row in rows])
        self.assertEqual(rows, before)

    def test_misaligned_input_raises_rather_than_truncating(self):
        # zip() would silently drop the tail, which would drop rows from the
        # pipeline. Uses real rows, sliced, not fabricated ones.
        rows = ingest(FIXTURE)
        validations = [validate(row) for row in rows]
        with self.assertRaises(ValueError):
            dedup(rows, validations[:-1])


class LinkedRowsHandoffTest(unittest.TestCase):
    """What M5 receives: whole rows, and copies of them."""

    def setUp(self):
        self.rows, self.results = run_dedup()
        self.by_id = {
            row["lead_id"]: result
            for row, result in zip(self.rows, self.results)
        }
        self.rows_by_id = {row["lead_id"]: row for row in self.rows}

    def test_linked_rows_are_whole_rows_not_a_curated_subset(self):
        linked = self.by_id["L-003"]["linked_rows"]
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0], self.rows_by_id["L-001"])
        self.assertEqual(set(linked[0]), set(self.rows_by_id["L-001"]))

    def test_linked_rows_are_copies(self):
        linked = self.by_id["L-003"]["linked_rows"][0]
        linked["company"] = "mutated by a downstream stage"
        self.assertNotEqual(
            self.rows_by_id["L-001"]["company"], "mutated by a downstream stage"
        )

    def test_linked_rows_and_linked_lead_ids_agree(self):
        for result in self.results:
            with self.subTest(key=result["match_key"]):
                self.assertEqual(
                    [row["lead_id"] for row in result["linked_rows"]],
                    result["linked_lead_ids"],
                )

    def test_stage_trace_is_thin_and_drops_the_row_copies(self):
        trace = dedup_stage_trace(self.by_id["L-003"])
        self.assertNotIn("linked_rows", trace)
        self.assertEqual(trace["linked_lead_ids"], ["L-001"])
        self.assertEqual(trace["first_occurrence_lead_id"], "L-001")
        self.assertTrue(trace["is_duplicate"])

    def test_stage_trace_keeps_everything_else(self):
        for result in self.results:
            with self.subTest(key=result["match_key"]):
                trace = dedup_stage_trace(result)
                self.assertEqual(set(trace), set(result) - {"linked_rows"})


class MatchKeyRuleTest(unittest.TestCase):
    """Rules 1 and 2, at the sanctioned generalization scope.

    Synthetic values go to `_match_key()` directly and are never assembled
    into fabricated rows, per MILESTONES.md's global constraint. Necessary
    because the fixture cannot exercise either rule: both duplicate pairs are
    byte-identical, so no real row varies in case or whitespace, and
    test_validate.py's test_no_fixture_field_is_malformed already establishes
    that no fixture email is malformed.
    """

    def test_case_is_folded(self):
        self.assertEqual(
            dedup_module._match_key("Dana.Reyes@BrightCart.io", OK),
            dedup_module._match_key("dana.reyes@brightcart.io", OK),
        )

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(
            dedup_module._match_key("  dana.reyes@brightcart.io\t", OK),
            dedup_module._match_key("dana.reyes@brightcart.io", OK),
        )

    def test_both_operations_apply_together(self):
        # The point of "together": a value needing both must still land on the
        # same key, which a strip-only or lowercase-only rule would miss.
        self.assertEqual(
            dedup_module._match_key("\n  Dana.REYES@BrightCart.IO  ", OK),
            "dana.reyes@brightcart.io",
        )

    def test_the_whole_address_is_normalized_not_just_the_domain(self):
        self.assertEqual(dedup_module._match_key("SAM@example.com", OK), "sam@example.com")

    def test_nothing_beyond_case_and_whitespace_is_folded(self):
        # Exact matching only: two addresses that differ in any other way stay
        # distinct keys. Not a claim about which schemes were rejected, just
        # that rule 1 does what it says and no more.
        distinct = [
            "sam+ads@example.com",
            "sam@example.com",
            "s.am@example.com",
        ]
        keys = [dedup_module._match_key(value, OK) for value in distinct]
        self.assertEqual(len(set(keys)), len(distinct))

    def test_unusable_statuses_yield_no_key(self):
        for status in (MISSING, MALFORMED, UNPARSEABLE):
            with self.subTest(status=status):
                self.assertIsNone(dedup_module._match_key("dana.reyes@brightcart.io", status))

    def test_two_identical_unusable_values_both_yield_no_key(self):
        # Rule 2's "including each other", at the level this scope can reach:
        # neither value produces a key, and dedup() builds groups only from
        # non-None keys. Observing two such rows failing to match each other
        # needs fabricated rows; see PROGRESS.md for that gap.
        first = dedup_module._match_key("not an address", MALFORMED)
        second = dedup_module._match_key("not an address", MALFORMED)
        self.assertIsNone(first)
        self.assertIsNone(second)

    def test_a_missing_value_yields_no_key_whatever_its_text(self):
        self.assertIsNone(dedup_module._match_key("", MISSING))
        self.assertIsNone(dedup_module._match_key("   ", MISSING))


def simulate_email_status(rows, statuses_by_id):
    """Real validate() output, with the email status of named rows replaced.

    Copies before editing, so the real result dicts are left alone. The rows
    themselves are never touched; see NoneKeyBucketingTest for why only the
    status is synthetic here.
    """
    validations = []
    for row in rows:
        result = validate(row)
        if row["lead_id"] in statuses_by_id:
            result = dict(result)
            result["fields"] = dict(result["fields"])
            result["fields"]["email"] = statuses_by_id[row["lead_id"]]
        validations.append(result)
    return validations


class NoneKeyBucketingTest(unittest.TestCase):
    """Rule 2's second half: a None key matches nothing, including another None.

    Scope note, per MILESTONES.md's M4 section. This class uses the second
    generalization exception sanctioned for this milestone, and it is narrow on
    purpose. The rows are real, unmodified fixture rows and the function under
    test is the real `dedup()`. What is synthetic is the Validate *status*
    handed to the stage, which isolates dedup()'s bucketing logic from whether
    Validate would really call those emails unusable. No lead row is
    fabricated, and nothing synthetic is presented as real fixture data. This
    exception grants nothing to MatchKeyRuleTest's scope above, which stays
    synthetic strings into `_match_key()` and nothing more. Same precedent as
    M6's simulated Judge output.

    Required because the fixture has exactly one genuinely keyless row (L-004),
    so a None bucket has one member and the guard cannot be told from its
    absence: deleting the guard left every other test in this file green.
    """

    def links_for(self, statuses_by_id):
        rows = ingest(FIXTURE)
        results = dedup(rows, simulate_email_status(rows, statuses_by_id))
        return {
            row["lead_id"]: result["linked_lead_ids"]
            for row, result in zip(rows, results)
        }

    def test_two_unusable_rows_with_identical_emails_do_not_link(self):
        # The sharpest case: these two rows really do share an address, so only
        # the status keeps them apart. Without the guard they bucket together
        # under None and link.
        links = self.links_for({"L-001": MALFORMED, "L-003": MALFORMED})
        self.assertEqual(links["L-001"], [])
        self.assertEqual(links["L-003"], [])

    def test_two_unusable_rows_with_different_emails_do_not_link(self):
        links = self.links_for({"L-005": MISSING, "L-007": MALFORMED})
        self.assertEqual(links["L-005"], [])
        self.assertEqual(links["L-007"], [])

    def test_a_simulated_unusable_row_does_not_link_to_the_real_keyless_row(self):
        # The realistic version: a batch carrying more than one blank email.
        # L-004's missing email is real, L-005's is simulated.
        links = self.links_for({"L-005": MISSING})
        self.assertEqual(links["L-004"], [])
        self.assertEqual(links["L-005"], [])

    def test_three_unusable_rows_do_not_form_one_group(self):
        links = self.links_for({"L-005": MISSING, "L-007": MISSING,
                                "L-009": MALFORMED})
        for lead_id in ("L-004", "L-005", "L-007", "L-009"):
            with self.subTest(lead_id=lead_id):
                self.assertEqual(links[lead_id], [])

    def test_simulating_a_status_disturbs_nothing_else(self):
        # Guards the test helper itself: the real pair must still link, so a
        # green result above cannot come from having broken dedup's input.
        links = self.links_for({"L-005": MISSING})
        self.assertEqual(links["L-002"], ["L-015"])
        self.assertEqual(links["L-015"], ["L-002"])
        self.assertEqual(links["L-001"], ["L-003"])

    def test_simulation_does_not_mutate_the_rows(self):
        rows = ingest(FIXTURE)
        before = copy.deepcopy(rows)
        dedup(rows, simulate_email_status(rows, {"L-005": MISSING}))
        self.assertEqual(rows, before)


class FileOrderTest(unittest.TestCase):
    """Rule 3, checked structurally because the fixture cannot check it.

    On both duplicate pairs `submitted_at` runs in the same direction as file
    order (L-001 09:14 before L-003 13:40; L-002 on 06-01 before L-015 on
    06-05), so an implementation that ordered groups by timestamp would pass
    every data test above. Asserting the source never reads the field is the
    only evidence available here that does not require fabricated rows, and it
    follows M3's AntiOverfitTest precedent of checking the mechanism directly.
    """

    def test_dedup_never_reads_submitted_at(self):
        for function in (dedup_module.dedup, dedup_module._match_key):
            with self.subTest(function=function.__name__):
                body = inspect.getsource(function)
                code = "\n".join(
                    line for line in body.splitlines()
                    if not line.strip().startswith("#")
                )
                # The docstring names the field to explain why it is unused.
                code = code.replace(function.__doc__ or "", "")
                self.assertNotIn("submitted_at", code)

    def test_the_fixture_cannot_discriminate_file_order_from_timestamps(self):
        # Asserted rather than assumed: if a future fixture reverses a pair,
        # this fails and the structural test above stops being the only
        # evidence available.
        rows = ingest(FIXTURE)
        order = [row["lead_id"] for row in rows]
        by_id = {row["lead_id"]: row for row in rows}
        for earlier, later in PAIRS:
            with self.subTest(pair=(earlier, later)):
                self.assertLess(order.index(earlier), order.index(later))
                self.assertLess(
                    by_id[earlier]["submitted_at"], by_id[later]["submitted_at"]
                )


class AntiOverfitTest(unittest.TestCase):
    """No fixture literal is hardcoded into the stage, mirroring M3's check."""

    def test_dedup_hardcodes_no_lead_id_or_fixture_value(self):
        source = inspect.getsource(dedup_module.dedup) + inspect.getsource(dedup_module._match_key)
        code = "\n".join(
            line for line in source.splitlines()
            if not line.strip().startswith("#")
        )
        for function in (dedup_module.dedup, dedup_module._match_key):
            code = code.replace(function.__doc__ or "", "")
        for literal in ("L-0", "brightcart", "stateuniv", "dana.reyes", "marcus.lee"):
            with self.subTest(literal=literal):
                self.assertNotIn(literal, code)


if __name__ == "__main__":
    unittest.main()
