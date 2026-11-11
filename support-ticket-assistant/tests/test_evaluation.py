"""Check that evaluation preserves inputs and does not hide partial failures."""

import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import evaluate
from ticket_assistant.engine import SearchEngine, load_tickets


ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = SearchEngine(load_tickets(ROOT / "data" / "tickets.json"), "solari-seed")
        cls.examples_path = ROOT / "data" / "new_tickets_example.json"

    def test_all_four_provider_inputs_are_preserved_verbatim(self):
        original = json.loads(self.examples_path.read_text(encoding="utf-8"))["new_tickets"]
        report = evaluate.evaluate_provided_examples(self.engine, self.examples_path)
        self.assertEqual([row["input"] for row in report["cases"]], original)

    def test_password_delivery_is_not_labeled_as_password_case_fix(self):
        class RelatedOnlyEngine:
            def search(self, *args, **kwargs):
                return {"results": [{"ticket": {"id": "T-1001"}}], "reason": "matches"}
        report = evaluate.evaluate_provided_examples(RelatedOnlyEngine(), self.examples_path)
        case = next(row for row in report["cases"] if row["id"] == "NT-1")
        self.assertEqual(case["relevant_ids"], [])
        self.assertEqual(case["related_ids"], ["T-1001"])
        self.assertFalse(case["passed"])

    def test_extra_suggestions_count_against_provided_precision(self):
        class MixedEngine:
            def search(self, title, *args, **kwargs):
                ids = ["T-1201", "T-1501"] if "revenue" in title else (["T-1303"] if "charged" in title else [])
                return {"results": [{"ticket": {"id": identifier}} for identifier in ids], "reason": "matches" if ids else "no_match"}
        report = evaluate.evaluate_provided_examples(MixedEngine(), self.examples_path)
        self.assertEqual(report["metrics"]["known_source_hits_at_3"], 2)
        self.assertEqual(report["metrics"]["labeled_suggestion_precision_on_known_examples"], 2 / 3)

    def test_nonzero_exit_preserves_complete_report_for_quality_failure(self):
        report = {"cases": [{"passed": False}], "provided_examples": {"cases": [{"passed": True}]}}
        output = io.StringIO()
        with patch("evaluate.evaluate", return_value=report), patch("sys.argv", ["evaluate.py", "--json"]), contextlib.redirect_stdout(output):
            self.assertEqual(evaluate.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), report)

    def test_metrics_keep_authored_and_provided_examples_separate(self):
        report = evaluate.evaluate(ROOT / "data" / "tickets.json", ROOT / "data" / "evaluation_queries.json", repeats=1)
        self.assertEqual(report["scope"]["history_records"], 40)
        self.assertEqual(report["scope"]["tenant_id"], "solari-seed")
        self.assertEqual(report["scope"]["positive_queries"], 12)
        self.assertEqual(report["scope"]["negative_queries"], 6)
        self.assertEqual(len(report["provided_examples"]["cases"]), 4)
        positive_cases = [case for case in report["cases"] if case["kind"] == "positive"]
        returned_count = sum(len(case["returned_ids"]) for case in positive_cases)
        relevant_count = sum(sum(identifier in case["relevant_ids"] for identifier in case["returned_ids"]) for case in positive_cases)
        self.assertEqual(report["metrics"]["total_returned_on_positives"], returned_count)
        self.assertEqual(report["metrics"]["labeled_relevant_returned_on_positives"], relevant_count)


if __name__ == "__main__":
    unittest.main()
