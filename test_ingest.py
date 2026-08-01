"""Acceptance tests for M1: Ingest.

Every assertion below runs against the real fixtures/inbound_leads.csv, per
CLAUDE.md. No synthetic or mocked rows.

Not covered here on purpose: ingest()'s header-mismatch ValueError. Exercising
it needs a CSV with a wrong header, which would be synthetic data, so that path
is deliberately left untested at M1 rather than tested against a fake file.
"""

import unittest
from pathlib import Path

from ingest import SCHEMA, ingest

FIXTURE = Path(__file__).parent / "fixtures" / "inbound_leads.csv"

EXPECTED_LEAD_IDS = [f"L-{n:03d}" for n in range(1, 21)]


class IngestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = ingest(FIXTURE)
        cls.by_id = {row["lead_id"]: row for row in cls.rows}

    def test_yields_twenty_rows_and_fixture_has_twenty_one_lines(self):
        self.assertEqual(len(self.rows), 20)
        lines = FIXTURE.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 21, "header + 20 data rows")

    def test_every_row_has_the_schema_columns_in_order(self):
        for row in self.rows:
            self.assertEqual(list(row.keys()), list(SCHEMA), row["lead_id"])

    def test_all_twenty_lead_ids_present_in_file_order(self):
        found = [row["lead_id"] for row in self.rows]
        self.assertEqual(set(found), set(EXPECTED_LEAD_IDS))
        self.assertEqual(found, EXPECTED_LEAD_IDS, "no row reordered")

    def test_duplicate_emails_pass_through_untouched(self):
        # Seeded duplicates. Linking them is M4's job; Ingest keeps all four
        # rows and does not collapse, drop, or annotate any of them.
        self.assertEqual(
            self.by_id["L-001"]["email"], self.by_id["L-003"]["email"]
        )
        self.assertEqual(self.by_id["L-001"]["email"], "dana.reyes@brightcart.io")
        self.assertEqual(
            self.by_id["L-002"]["email"], self.by_id["L-015"]["email"]
        )
        self.assertEqual(
            self.by_id["L-002"]["email"], "marcus.lee.2027@stateuniv.edu"
        )

    def test_malformed_and_blank_cells_are_not_mutated(self):
        self.assertEqual(
            self.by_id["L-012"]["submitted_at"], "2026-13-45T99:99:00Z"
        )
        self.assertEqual(self.by_id["L-018"]["message"], "")
        self.assertEqual(self.by_id["L-005"]["monthly_budget_usd"], "we'll discuss")
        self.assertEqual(self.by_id["L-017"]["monthly_budget_usd"], "15k")

        # L-004 is the only blank email in the fixture. L-008 carries a real
        # personal-provider address with a blank company and website, which is
        # a different shape of problem entirely. See PROGRESS.md's M1 note.
        self.assertEqual(self.by_id["L-004"]["email"], "")
        self.assertEqual(self.by_id["L-008"]["email"], "rickalvarez88@gmail.com")
        for lead_id in ("L-002", "L-008", "L-015", "L-019"):
            self.assertEqual(self.by_id[lead_id]["company"], "", lead_id)
        for lead_id in ("L-002", "L-008", "L-010", "L-013", "L-015", "L-019"):
            self.assertEqual(self.by_id[lead_id]["website"], "", lead_id)

    def test_values_stay_raw_strings_with_no_coercion(self):
        # "0" must not become 0 and "25000" must not become 25000: whether a
        # budget parses is M2's question, and it cannot ask it if Ingest
        # already answered it.
        for lead_id in ("L-002", "L-019"):
            self.assertEqual(self.by_id[lead_id]["monthly_budget_usd"], "0", lead_id)
        self.assertEqual(self.by_id["L-001"]["monthly_budget_usd"], "25000")

        for row in self.rows:
            self.assertEqual(len(row), len(SCHEMA), row["lead_id"])
            self.assertNotIn("_extra_fields", row, row["lead_id"])
            for column, value in row.items():
                self.assertIsInstance(value, str, f"{row['lead_id']}.{column}")

    def test_unicode_and_html_entities_survive_intact(self):
        self.assertEqual(self.by_id["L-009"]["name"], "Lucía Fernández")
        self.assertIn("México", self.by_id["L-009"]["message"])

        l016 = self.by_id["L-016"]["message"]
        self.assertIn("👋👋", l016)
        self.assertIn("🔥🔥", l016)
        # Unescaping &amp; is a content decision, not a read-the-file decision.
        self.assertIn("&amp;", l016)


if __name__ == "__main__":
    unittest.main()
