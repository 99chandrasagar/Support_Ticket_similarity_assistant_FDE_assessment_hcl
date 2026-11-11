"""Validate the supplied starter schema without inventing source metadata."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from ticket_assistant.engine import SearchEngine, load_tickets


ROOT = Path(__file__).resolve().parents[1]


class SuppliedSeedAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT / "data" / "tickets.json").read_text(encoding="utf-8"))
        cls.records = load_tickets(ROOT / "data" / "tickets.json")
        cls.incoming = json.loads((ROOT / "data" / "new_tickets_example.json").read_text(encoding="utf-8"))["new_tickets"]

    def load_payload(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return load_tickets(path)

    def test_supplied_records_preserve_source_fields_and_dates(self):
        self.assertEqual(len(self.records), 40)
        for source, actual in zip(self.source["tickets"], self.records):
            with self.subTest(ticket=source["ticket_id"]):
                for original, normalized in (
                    ("ticket_id", "id"), ("subject", "title"),
                    ("description", "description"), ("resolution_notes", "resolution"),
                    ("category", "category"), ("tags", "tags"),
                    ("created_at", "created_at"), ("status", "status"),
                ):
                    self.assertEqual(actual[normalized], source[original])
                self.assertEqual(actual["product"], source["category"])
                self.assertIsNone(actual["resolved_at"])
                self.assertEqual(actual["tenant_id"], "solari-seed")
                self.assertEqual(actual["scope_kind"], "dataset")
                self.assertEqual(actual["source_schema"], "assessment_seed")

    def test_seed_scope_is_not_mixed_with_demo_customer_scope(self):
        engine = SearchEngine(self.records, "solari-seed")
        self.assertEqual(engine.search("revenue chart")["total_eligible"], 40)
        self.assertEqual(SearchEngine(self.records, "solari-demo").search("revenue chart")["results"], [])

    def test_source_resolution_is_returned_verbatim_without_resolution_date(self):
        query = next(q for q in self.incoming if q["ticket_id"] == "NT-3")
        result = SearchEngine(self.records, "solari-seed").search(query["subject"], query["description"])
        best = result["results"][0]["ticket"]
        source = next(t for t in self.source["tickets"] if t["ticket_id"] == "T-1303")
        self.assertEqual(best["id"], "T-1303")
        self.assertEqual(best["resolution"], source["resolution_notes"])
        self.assertEqual(best["created_at"], source["created_at"])
        self.assertIsNone(best["resolved_at"])

    def test_unseen_snowflake_integration_abstains_without_special_case(self):
        query = next(q for q in self.incoming if q["ticket_id"] == "NT-4")
        result = SearchEngine(self.records, "solari-seed").search(query["subject"], query["description"])
        self.assertEqual(result["reason"], "no_match")
        self.assertEqual(result["results"], [])

    def test_category_filter_uses_source_category(self):
        result = SearchEngine(self.records, "solari-seed").search("chart revenue dashboard", product="render")
        self.assertTrue(result["results"])
        self.assertTrue(all(row["ticket"]["category"] == "render" for row in result["results"]))
        self.assertEqual(result["total_eligible"], 5)

    def test_missing_or_invalid_seed_fields_fail_clearly(self):
        first = self.source["tickets"][0]
        missing = dict(first)
        del missing["resolution_notes"]
        bad_records = [
            missing, dict(first, subject=None), dict(first, ticket_id=" "),
            dict(first, tags="login"), dict(first, tags=[7]),
            dict(first, tags=[" "]), dict(first, created_at="2025-02-30"),
            dict(first, created_at=None), dict(first, created_at="2025-10-03T12:00:00Z"),
        ]
        for record in bad_records:
            with self.subTest(record=record), self.assertRaises(ValueError):
                self.load_payload({"tickets": [record]})

    def test_invalid_wrapper_and_incoming_payload_are_not_silently_empty(self):
        for payload in ({}, {"new_tickets": []}, {"tickets": None}, {"tickets": {}}, {"tickets": [None]}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.load_payload(payload)

    def test_duplicate_seed_ids_are_rejected(self):
        source = self.source["tickets"][0]
        with self.assertRaises(ValueError):
            self.load_payload({"tickets": [source, source]})

    def test_escaped_unpaired_surrogates_are_rejected_before_output_encoding(self):
        first = self.source["tickets"][0]
        for field, bad_value in (("subject", "\ud800"), ("resolution_notes", "\udfff"), ("tags", ["\ud800"])):
            with self.subTest(schema="seed", field=field), self.assertRaisesRegex(ValueError, "valid Unicode"):
                self.load_payload({"tickets": [dict(first, **{field: bad_value})]})
        canonical = {
            "id": "UTF8-1", "tenant_id": "customer", "title": "Revenue chart blank",
            "description": "No bars appear.", "product": "Dashboards", "status": "resolved",
            "resolution": "Corrected the filter.", "resolved_at": "2025-10-10",
        }
        for field in ("title", "resolution", "tenant_id"):
            with self.subTest(schema="canonical", field=field), self.assertRaisesRegex(ValueError, "valid Unicode"):
                self.load_payload([dict(canonical, **{field: "\ud800"})])

    def test_valid_empty_history_abstains(self):
        records = self.load_payload({"tickets": []})
        result = SearchEngine(records, "solari-seed").search("revenue chart")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["total_eligible"], 0)

    def test_seed_records_with_real_tenant_identity_are_not_overwritten(self):
        source = dict(self.source["tickets"][0], tenant_id="actual-customer")
        with self.assertRaises(ValueError):
            self.load_payload({"tickets": [source]})
        legacy = {
            "id": "REAL-1", "tenant_id": "actual-customer", "title": "Revenue chart blank",
            "description": "No revenue bars appear.", "product": "Dashboards", "status": "resolved",
            "resolution": "Corrected the filter.", "resolved_at": "2025-10-10",
        }
        records = self.load_payload([legacy])
        self.assertEqual(records[0]["tenant_id"], "actual-customer")
        self.assertTrue(SearchEngine(records, "actual-customer").search("revenue chart")["results"])

    def test_nested_tag_mutation_does_not_change_index_state(self):
        source = deepcopy(self.records)
        engine = SearchEngine(source, "solari-seed")
        source[0]["tags"].append("input-corruption")
        result = engine.search("password reset", product="auth")
        self.assertTrue(result["results"])
        result["results"][0]["ticket"]["tags"].append("output-corruption")
        repeated = json.dumps(engine.search("password reset", product="auth"))
        self.assertNotIn("input-corruption", repeated)
        self.assertNotIn("output-corruption", repeated)

    def test_unresolved_and_empty_seed_resolutions_are_ineligible(self):
        first = self.source["tickets"][0]
        records = self.load_payload({"tickets": [
            dict(first, ticket_id="OPEN-1", status="open"),
            dict(first, ticket_id="EMPTY-1", resolution_notes=""),
        ]})
        result = SearchEngine(records, "solari-seed").search("password reset")
        self.assertEqual(result["total_eligible"], 0)
        self.assertEqual(result["results"], [])


if __name__ == "__main__":
    unittest.main()
