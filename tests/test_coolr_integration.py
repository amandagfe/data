import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CoolrIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))

    def test_reconciled_identity_counts(self):
        events = self.catalog["events"]
        ids = [event["event_id"] for event in events]
        self.assertEqual(len(events), 14753)
        self.assertEqual(len(set(ids)), 14753)
        self.assertEqual(
            self.catalog["source"]["origins"],
            {"coolr_only": 3720, "coolr_supersedes_local": 11030, "glc_local_only": 3},
        )

    def test_missing_values_and_period_are_explicit(self):
        quality = self.catalog["quality"]
        self.assertEqual(quality["period"], {"min": "1915-12-15", "max": "2025-05-18"})
        self.assertEqual(quality["missing_dates"], 1637)
        self.assertEqual(quality["invalid_coordinates"], 27)
        self.assertEqual(quality["duplicate_event_ids"], [])

    def test_integration_never_uses_proximity_as_identity(self):
        policy = self.catalog["source"]["policy"]
        self.assertIn("same_event_id", policy)
        self.assertIn("never_deduplicate_by_date_or_coordinate", policy)


if __name__ == "__main__":
    unittest.main()
