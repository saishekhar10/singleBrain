"""Acceptance tests for M2: Validate.

Every row-level assertion below runs against the real fixtures/inbound_leads.csv,
per CLAUDE.md. No fabricated lead rows anywhere in this file.

One deliberate exception, and the distinction matters. MalformedValueTest at the
bottom passes synthetic *field values* to the per-field checker functions
directly. It never assembles them into a fabricated lead row, and no row-level
behavior is asserted against invented data. This is the generalization test
MILESTONES.md's global constraint sanctions for M2, and it is necessary rather
than optional: under the shape-only rule settled 2026-07-31, no field in any of
the 20 fixture rows is malformed, so without it the MALFORMED branch would ship
with zero coverage. FixtureFieldTest asserts that emptiness directly, so if a
future fixture does contain a malformed value, this file says so out loud
instead of silently drifting.
"""

import copy
import unittest
from pathlib import Path

from pipeline.constants import MALFORMED, MISSING, OK, UNPARSEABLE
from pipeline.ingest import ingest
from pipeline.validate import (
    CRITERIA_FIELDS,
    DOMAIN_SIGNALS,
    email_domain_is_personal_provider,
    is_disposable_email_domain,
    is_reserved_or_example_domain,
    validate,
    validate_budget,
    validate_company,
    validate_email,
    validate_message,
    validate_website,
)

FIXTURE = (Path(__file__).resolve().parent.parent
           / "fixtures" / "inbound_leads.csv")

ALL_LEAD_IDS = [f"L-{n:03d}" for n in range(1, 21)]


class ValidateTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = ingest(FIXTURE)
        cls.by_id = {row["lead_id"]: row for row in cls.rows}
        cls.results = {row["lead_id"]: validate(row) for row in cls.rows}

    def status(self, lead_id, field):
        return self.results[lead_id]["fields"][field]

    def assertFieldStatuses(self, field, expected_by_status):
        """Assert the status of `field` on all 20 rows at once.

        Checking every row rather than only the cited ones is the point: a
        false positive on an unlisted row is exactly as wrong as a miss on a
        listed one, and only a full sweep catches it.
        """
        for lead_id in ALL_LEAD_IDS:
            expected = next(
                (s for s, ids in expected_by_status.items() if lead_id in ids), OK
            )
            self.assertEqual(
                self.status(lead_id, field), expected, f"{lead_id}.{field}"
            )


class FixtureFieldTest(ValidateTestBase):
    def test_email_statuses(self):
        # L-004 is the only blank email. L-008 carries a real personal-provider
        # address and must come back OK, not missing: see PROGRESS.md's M1
        # finding, where the opposite claim in the criteria was the bug.
        self.assertFieldStatuses("email", {MISSING: {"L-004"}})
        self.assertEqual(self.status("L-008", "email"), OK)
        # Shape only, settled 2026-07-31: asdf@asdf.com is well-formed. Whether
        # it is plausible is Section 5 criterion 1's question, for the Judge.
        self.assertEqual(self.by_id["L-010"]["email"], "asdf@asdf.com")
        self.assertEqual(self.status("L-010", "email"), OK)

    def test_website_statuses(self):
        self.assertFieldStatuses(
            "website",
            {MISSING: {"L-002", "L-008", "L-010", "L-013", "L-015", "L-019"}},
        )

    def test_company_statuses(self):
        self.assertFieldStatuses(
            "company", {MISSING: {"L-002", "L-008", "L-015", "L-019"}}
        )
        # "asdf" is a legible company name of low plausibility, which is a
        # judgment for M5, not a shape defect for M2.
        self.assertEqual(self.by_id["L-010"]["company"], "asdf")
        self.assertEqual(self.status("L-010", "company"), OK)

    def test_message_statuses(self):
        self.assertFieldStatuses("message", {MISSING: {"L-018"}})
        # Both of these are legible text and therefore OK: L-010's is
        # meaningless, L-016's is HTML-wrapped with emoji and an HTML entity.
        self.assertEqual(self.status("L-010", "message"), OK)
        self.assertIn("<div>", self.by_id["L-016"]["message"])
        self.assertIn("&amp;", self.by_id["L-016"]["message"])
        self.assertEqual(self.status("L-016", "message"), OK)

    def test_budget_statuses_and_parsed_values(self):
        self.assertFieldStatuses(
            "monthly_budget_usd", {UNPARSEABLE: {"L-005"}}
        )
        self.assertIsNone(self.results["L-005"]["budget_value"])

        # Decision 1, settled 2026-07-31: k/K multiplies by 1000, so L-017
        # parses rather than escalating on an unparseable budget.
        self.assertEqual(self.by_id["L-017"]["monthly_budget_usd"], "15k")
        self.assertEqual(self.status("L-017", "monthly_budget_usd"), OK)
        self.assertEqual(self.results["L-017"]["budget_value"], 15000)

        # "0" is a real submitted number, not a missing or unparseable one.
        # Whether it clears the floor is M5's threshold question.
        for lead_id in ("L-002", "L-019"):
            self.assertEqual(self.status(lead_id, "monthly_budget_usd"), OK, lead_id)
            self.assertEqual(self.results[lead_id]["budget_value"], 0, lead_id)

        self.assertEqual(self.results["L-001"]["budget_value"], 25000)
        self.assertEqual(self.results["L-010"]["budget_value"], 999999)

    def test_no_fixture_field_is_malformed(self):
        # Asserted rather than assumed, because it is the reason
        # MalformedValueTest below exists at all. If a future fixture breaks
        # this, that test's synthetic coverage stops being the only coverage
        # and this assertion is where it shows up first.
        for lead_id in ALL_LEAD_IDS:
            for field in CRITERIA_FIELDS:
                self.assertNotEqual(
                    self.status(lead_id, field), MALFORMED, f"{lead_id}.{field}"
                )

    def assertSignalFiresOnlyOn(self, signal, lead_id):
        """The signal is True on that row, False everywhere with a domain."""
        for other in ALL_LEAD_IDS:
            expected = None if other == "L-004" else other == lead_id
            self.assertIs(self.results[other][signal], expected, f"{signal}/{other}")

    def test_personal_provider_signal(self):
        self.assertEqual(self.by_id["L-008"]["email"], "rickalvarez88@gmail.com")
        self.assertSignalFiresOnlyOn("email_domain_is_personal_provider", "L-008")

    def test_disposable_signal(self):
        self.assertEqual(self.by_id["L-013"]["email"], "jblake@mailinator.com")
        self.assertSignalFiresOnlyOn("is_disposable_email_domain", "L-013")

    def test_reserved_or_example_signal(self):
        self.assertEqual(self.by_id["L-019"]["email"], "h.vogel@example.de")
        self.assertSignalFiresOnlyOn("is_reserved_or_example_domain", "L-019")

    def test_signals_are_none_together_when_there_is_no_domain(self):
        # None where there is no domain to read, not False: the two are
        # different facts and Section 6 keeps them apart. L-004's email is
        # blank, so all three report None rather than a negative result.
        for signal in DOMAIN_SIGNALS:
            self.assertIsNone(self.results["L-004"][signal], signal)

    def test_the_three_signals_stay_distinct_and_do_not_overlap(self):
        # The reason they are three fields and not one merged flag: each fires
        # on a different row, and merging them would erase which one fired.
        fired_by_row = {
            lead_id: [s for s in DOMAIN_SIGNALS if self.results[lead_id][s]]
            for lead_id in ALL_LEAD_IDS
        }
        for lead_id, fired in fired_by_row.items():
            self.assertLessEqual(len(fired), 1, f"{lead_id} fired {fired}")
        self.assertEqual(
            {lead_id: fired[0] for lead_id, fired in fired_by_row.items() if fired},
            {
                "L-008": "email_domain_is_personal_provider",
                "L-013": "is_disposable_email_domain",
                "L-019": "is_reserved_or_example_domain",
            },
        )


class CrashSafetyTest(ValidateTestBase):
    def test_invalid_submitted_at_does_not_raise_or_leak(self):
        self.assertEqual(self.by_id["L-012"]["submitted_at"], "2026-13-45T99:99:00Z")
        self.assertFalse(self.results["L-012"]["submitted_at_valid"])
        # The broken timestamp annotates the row and changes nothing else: all
        # five criteria-feeding fields on L-012 are OK, per SPEC.md Section 5's
        # scope note.
        for field in CRITERIA_FIELDS:
            self.assertEqual(self.status("L-012", field), OK, field)

    def test_every_other_row_has_a_valid_timestamp(self):
        for lead_id in ALL_LEAD_IDS:
            if lead_id == "L-012":
                continue
            self.assertTrue(self.results[lead_id]["submitted_at_valid"], lead_id)

    def test_validating_all_twenty_rows_raises_nothing(self):
        for row in self.rows:
            validate(row)


class ContractTest(ValidateTestBase):
    def test_validate_does_not_mutate_the_row(self):
        # Extends M1's guarantee through this stage: ingest() promises raw
        # untouched strings, and Validate must not quietly strip or coerce them
        # on the way past.
        rows = ingest(FIXTURE)
        before = copy.deepcopy(rows)
        for row in rows:
            validate(row)
        self.assertEqual(rows, before)

    def test_result_covers_exactly_the_five_criteria_fields(self):
        for lead_id in ALL_LEAD_IDS:
            fields = self.results[lead_id]["fields"]
            self.assertEqual(tuple(fields), CRITERIA_FIELDS, lead_id)

    def test_every_status_is_one_of_the_four_values(self):
        allowed = {OK, MISSING, MALFORMED, UNPARSEABLE}
        for lead_id in ALL_LEAD_IDS:
            for field, status in self.results[lead_id]["fields"].items():
                self.assertIn(status, allowed, f"{lead_id}.{field}")

    def test_budget_value_is_present_exactly_when_the_budget_parsed(self):
        for lead_id in ALL_LEAD_IDS:
            result = self.results[lead_id]
            parsed = result["fields"]["monthly_budget_usd"] == OK
            self.assertEqual(result["budget_value"] is not None, parsed, lead_id)

    def test_no_fixture_row_is_ragged(self):
        for lead_id in ALL_LEAD_IDS:
            self.assertIsNone(self.results[lead_id]["extra_fields"], lead_id)


class MalformedValueTest(unittest.TestCase):
    """Synthetic field values, not fabricated rows. See this file's docstring.

    Sanctioned by MILESTONES.md's global constraint, which names M2 as one of
    three milestones where a generalization test is allowed. Each value below
    probes the shape rule itself rather than any lead.
    """

    def test_email_shape_failures(self):
        for value in (
            "dana.reyes",  # no @ at all
            "@brightcart.io",  # empty local part
            "dana@",  # empty domain part
            "dana@brightcart",  # no dot in the domain
            "dana@brightcart..io",  # empty domain label
            "dana a@brightcart.io",  # whitespace inside
            "dana@a@brightcart.io",  # two @
        ):
            self.assertEqual(validate_email(value), MALFORMED, value)

    def test_email_shapes_that_must_stay_ok(self):
        for value in (
            "dana.reyes@brightcart.io",
            "  dana.reyes@brightcart.io  ",  # surrounding whitespace only
            "dana+tag@brightcart.co.uk",
        ):
            self.assertEqual(validate_email(value), OK, value)

    def test_website_shape_failures(self):
        for value in (
            "not a url at all",  # prose, whitespace inside
            "brightcart",  # no dot
            "https://",  # no host
        ):
            self.assertEqual(validate_website(value), MALFORMED, value)

    def test_website_shapes_that_must_stay_ok(self):
        # A missing scheme is not a data defect, only a shorthand.
        for value in (
            "https://brightcart.io",
            "http://brightcart.io/pricing?ref=1",
            "brightcart.io",
            "www.brightcart.io:8080/path",
        ):
            self.assertEqual(validate_website(value), OK, value)

    def test_control_characters_are_the_only_free_text_malformation(self):
        for checker in (validate_company, validate_message):
            self.assertEqual(checker("Bright\x00Cart"), MALFORMED)
            self.assertEqual(checker("Bright\x07Cart"), MALFORMED)
            self.assertEqual(checker("Bright�Cart"), MALFORMED)
            # Tab, newline, and carriage return are ordinary text.
            self.assertEqual(checker("line one\nline two\r\n\tindented"), OK)

    def test_whitespace_only_cells_are_missing_on_every_field(self):
        for checker in (
            validate_email,
            validate_website,
            validate_company,
            validate_message,
        ):
            self.assertEqual(checker("   "), MISSING, checker.__name__)
            self.assertEqual(checker(""), MISSING, checker.__name__)
            # None arrives on a short ragged row, which M1 leaves for M2.
            self.assertEqual(checker(None), MISSING, checker.__name__)
        for value in ("   ", "", None):
            self.assertEqual(validate_budget(value), (MISSING, None), repr(value))

    def test_budget_accepts_only_the_k_suffix(self):
        self.assertEqual(validate_budget("15k"), (OK, 15000))
        self.assertEqual(validate_budget("15K"), (OK, 15000))
        self.assertEqual(validate_budget("1.5k"), (OK, 1500))
        # Every other suffix is unparseable, m/M explicitly included.
        for value in ("15m", "15M", "15 k", "15kk", "15k/mo", "15,000 USD", "15b"):
            self.assertEqual(validate_budget(value), (UNPARSEABLE, None), value)

    def test_budget_numeric_forms(self):
        self.assertEqual(validate_budget("25000"), (OK, 25000))
        self.assertEqual(validate_budget("$15,000"), (OK, 15000))
        self.assertEqual(validate_budget("  2500.50  "), (OK, 2500.50))
        self.assertEqual(validate_budget("-500"), (OK, -500))
        self.assertEqual(validate_budget("0"), (OK, 0))

    def test_budget_shapes_that_do_not_parse_at_the_checker_level(self):
        for value in (
            "we'll discuss",  # the L-005 shape, as a checker-level case
            "1,5,00",  # malformed thousands grouping
            "12.34.56",  # two decimal points
            "$",  # no digits
            "TBD",
        ):
            self.assertEqual(validate_budget(value), (UNPARSEABLE, None), value)


class DomainSignalRuleTest(unittest.TestCase):
    """Synthetic email addresses, not fabricated rows. Same sanction and same
    scope as MalformedValueTest above.

    The fixture gives each of the three signals exactly one True row, so real
    rows prove the signals fire, not that the rules behind them generalize.
    These cases probe the rules themselves, including the two boundaries
    `is_reserved_or_example_domain` deliberately draws.
    """

    def signal(self, checker, email):
        # Runs the real validate_email first, so the status handed to the
        # signal is the one validate() would hand it, not a stand-in.
        return checker(email, validate_email(email))

    def test_disposable_domains_fire_and_others_do_not(self):
        for email in (
            "jblake@mailinator.com",
            "someone@guerrillamail.com",
            "someone@yopmail.com",
            "SOMEONE@Mailinator.com",  # case-insensitive
        ):
            self.assertIs(self.signal(is_disposable_email_domain, email), True, email)
        for email in ("dana@brightcart.io", "rick@gmail.com", "h.vogel@example.de"):
            self.assertIs(self.signal(is_disposable_email_domain, email), False, email)

    def test_reserved_tlds_and_the_example_convention_both_fire(self):
        for email in (
            "a@example.com",  # RFC 2606, literal
            "a@example.net",
            "a@example.org",
            "a@example.de",  # not RFC-reserved, same convention
            "a@example.io",
            "a@anything.test",  # RFC 6761 special-use TLDs
            "a@anything.invalid",
            "a@anything.localhost",
            "a@anything.local",  # RFC 6762 mDNS
        ):
            self.assertIs(self.signal(is_reserved_or_example_domain, email), True, email)

    def test_reserved_signal_boundaries(self):
        # Documented cap: a real company's subdomain is not a placeholder.
        self.assertIs(
            self.signal(is_reserved_or_example_domain, "a@example.mycompany.com"), False
        )
        # Documented gap, asserted so it stays visible rather than becoming a
        # surprise later: a placeholder under a multi-part suffix is missed,
        # because separating those needs a public suffix list.
        self.assertIs(
            self.signal(is_reserved_or_example_domain, "a@example.co.uk"), False
        )
        for email in ("dana@brightcart.io", "asdf@asdf.com", "rick@gmail.com"):
            self.assertIs(
                self.signal(is_reserved_or_example_domain, email), False, email
            )

    def test_all_three_signals_report_none_when_there_is_no_domain(self):
        checkers = (
            email_domain_is_personal_provider,
            is_disposable_email_domain,
            is_reserved_or_example_domain,
        )
        # Blank, whitespace-only, absent, and malformed alike: no domain was
        # ever read, so None rather than False.
        for email in ("", "   ", None, "not-an-email", "a@b", "dana@@brightcart.io"):
            for checker in checkers:
                self.assertIsNone(
                    self.signal(checker, email), f"{checker.__name__}({email!r})"
                )

    def test_personal_provider_rule(self):
        for email in ("rick@gmail.com", "a@YAHOO.com", "a@icloud.com"):
            self.assertIs(
                self.signal(email_domain_is_personal_provider, email), True, email
            )
        # Neither of the other two categories counts as consumer webmail.
        for email in ("jblake@mailinator.com", "h.vogel@example.de", "a@brightcart.io"):
            self.assertIs(
                self.signal(email_domain_is_personal_provider, email), False, email
            )


if __name__ == "__main__":
    unittest.main()
