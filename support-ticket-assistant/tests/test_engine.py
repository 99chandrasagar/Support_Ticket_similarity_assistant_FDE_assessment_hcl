"""Behavioral checks for retrieval boundaries and untrusted input."""

import json
from pathlib import Path
import tempfile
import unittest

from ticket_assistant.engine import SearchEngine, load_tickets


ROOT = Path(__file__).resolve().parents[1]


def ticket(identifier="T-1", **overrides):
    record = {
        "id": identifier, "tenant_id": "solari-demo",
        "title": "SAML certificate expired", "description": "Identity login fails with invalid signature.",
        "product": "Identity", "status": "resolved",
        "resolution": "An authorized administrator renewed the signing certificate.",
        "resolved_at": "2026-10-15",
    }
    record.update(overrides)
    return record


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_tickets(ROOT / "tests" / "fixtures" / "demo_tickets.json")
        cls.engine = SearchEngine(cls.records, "solari-demo")

    def test_known_issue_surfaces_recorded_resolution(self):
        result = self.engine.search("SAML certificate invalid signature")
        self.assertEqual(result["reason"], "matches")
        self.assertEqual(result["results"][0]["ticket"]["id"], "DEMO-001")
        self.assertIn("certificate", result["results"][0]["matched_terms"])
        self.assertIn("administrator", result["results"][0]["ticket"]["resolution"])

    def test_other_tenants_never_appear(self):
        for query in ("SAML certificate invalid signature", "BigQuery 403 dataset permissions", "API 429 rate limit", "scheduled report email missing"):
            with self.subTest(query=query):
                result = self.engine.search(query, limit=10)
                self.assertTrue(result["results"])
                self.assertTrue(all(item["ticket"]["tenant_id"] == "solari-demo" for item in result["results"]))
                self.assertNotIn("OTHER TENANT ONLY", json.dumps(result))

    def test_other_tenants_do_not_influence_scores_or_index_statistics(self):
        own = [r for r in self.records if r["tenant_id"] == "solari-demo"]
        base = SearchEngine(own, "solari-demo")
        query = "SAML certificate invalid signature"
        self.assertEqual(base.search(query), self.engine.search(query))

    def test_unknown_tenant_has_no_results(self):
        result = SearchEngine(self.records, "unconfigured-tenant").search("SAML certificate")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["total_eligible"], 0)

    def test_open_and_missing_resolution_records_are_excluded(self):
        for query in ("SAML certificate invalid signature", "API 429 sync", "BigQuery 403 permissions", "duplicate webhook event"):
            with self.subTest(query=query):
                result = self.engine.search(query, limit=10)
                ids = {item["ticket"]["id"] for item in result["results"]}
                self.assertTrue(ids.isdisjoint({"DEMO-025", "DEMO-026", "DEMO-027", "DEMO-028"}))
                self.assertEqual(result["total_eligible"], 24)

    def test_resolution_text_is_not_used_for_retrieval(self):
        record = ticket(resolution="quasar zebra special fix")
        engine = SearchEngine([record], "solari-demo")
        self.assertEqual(engine.search("quasar zebra")["results"], [])
        self.assertTrue(engine.search("SAML certificate")["results"])

    def test_empty_or_boilerplate_query_abstains(self):
        for query in ("", "   ", "please help", "ticket issue"):
            with self.subTest(query=query):
                result = self.engine.search(query)
                self.assertEqual(result["results"], [])
                self.assertEqual(result["reason"], "insufficient_query")

    def test_out_of_domain_query_abstains(self):
        result = self.engine.search("coffee machine leaking kitchen water")
        self.assertEqual(result["reason"], "no_match")
        self.assertEqual(result["results"], [])

    def test_one_generic_term_does_not_trigger_suggestion(self):
        self.assertEqual(self.engine.search("dashboard")["results"], [])

    def test_distinctive_error_identifier_can_match_alone(self):
        engine = SearchEngine([ticket(title="Service failure ERR_AUTH_401")], "solari-demo")
        result = engine.search("ERR_AUTH_401")
        self.assertEqual(result["results"][0]["ticket"]["id"], "T-1")
        self.assertEqual(engine.search("ERR_AUTH_402")["results"], [])

    def test_ticket_self_exclusion(self):
        result = self.engine.search("SAML certificate invalid signature", exclude_ticket_id="DEMO-001")
        self.assertNotIn("DEMO-001", [item["ticket"]["id"] for item in result["results"]])
        self.assertEqual(result["total_eligible"], 23)

    def test_product_filter_is_applied_before_results(self):
        result = self.engine.search("SAML certificate invalid signature", product="Identity")
        self.assertTrue(result["results"])
        self.assertTrue(all(item["ticket"]["product"] == "Identity" for item in result["results"]))
        self.assertEqual(result["total_eligible"], 3)
        self.assertEqual(self.engine.search("SAML certificate invalid signature", product="API")["results"], [])

    def test_ranking_is_deterministic_even_if_input_order_changes(self):
        records = [ticket("T-2"), ticket("T-1")]
        first = SearchEngine(records, "solari-demo").search("SAML certificate")
        second = SearchEngine(list(reversed(records)), "solari-demo").search("SAML certificate")
        self.assertEqual(first, second)
        self.assertEqual([item["ticket"]["id"] for item in first["results"]], ["T-1", "T-2"])

    def test_results_cannot_mutate_future_responses(self):
        engine = SearchEngine([ticket()], "solari-demo")
        first = engine.search("SAML certificate")
        first["results"][0]["ticket"]["resolution"] = "corrupted"
        self.assertNotEqual(engine.search("SAML certificate")["results"][0]["ticket"]["resolution"], "corrupted")

    def test_input_mutation_does_not_change_index(self):
        source = [ticket()]
        engine = SearchEngine(source, "solari-demo")
        source[0]["resolution"] = "corrupted"
        self.assertNotEqual(engine.search("SAML certificate")["results"][0]["ticket"]["resolution"], "corrupted")

    def test_limit_validation_rejects_bool_and_out_of_range(self):
        for value in (True, 0, -1, 11, 1.5, "3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.engine.search("SAML certificate", limit=value)

    def test_query_validation_rejects_bad_types_and_oversized_text(self):
        for title, description in ((None, ""), ([], ""), ("title", {}), ("x" * 10001, "")):
            with self.subTest(title_type=type(title).__name__), self.assertRaises(ValueError):
                self.engine.search(title, description)

    def test_duplicate_ids_within_tenant_are_rejected(self):
        with self.assertRaises(ValueError):
            SearchEngine([ticket(), ticket()], "solari-demo")

    def test_same_id_in_different_tenants_is_valid(self):
        engine = SearchEngine([ticket(), ticket(tenant_id="other-demo")], "solari-demo")
        self.assertEqual(engine.search("SAML certificate")["total_eligible"], 1)

    def test_malformed_ticket_schema_is_rejected(self):
        missing = ticket()
        del missing["resolution"]
        for bad in (missing, ticket(title=None), ticket(id=" "), ticket(resolved_at="2026-02-30"), ticket(resolved_at=None)):
            with self.subTest(record=bad), self.assertRaises(ValueError):
                SearchEngine([bad], "solari-demo")

    def test_load_rejects_invalid_json_and_wrong_root_type(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for text in ("{oops", "{}", "[null]"):
                with self.subTest(text=text):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_tickets(path)

    def test_unknown_fields_are_not_leaked(self):
        record = ticket(internal_secret="do-not-return")
        result = SearchEngine([record], "solari-demo").search("SAML certificate")
        self.assertNotIn("internal_secret", result["results"][0]["ticket"])


if __name__ == "__main__":
    unittest.main()
