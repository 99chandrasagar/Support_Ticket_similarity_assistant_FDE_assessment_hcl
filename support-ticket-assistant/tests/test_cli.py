import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "ticket_assistant", *arguments],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=15,
        )

    def test_json_search_is_parseable(self):
        result = self.run_cli("search", "--title", "Charged twice for the same billing cycle", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["reason"], "matches")
        self.assertTrue(payload["results"])
        for match in payload["results"]:
            self.assertEqual(match["ticket"]["tenant_id"], "solari-seed")
        self.assertEqual(payload["results"][0]["ticket"]["id"], "T-1303")

    def test_demo_explains_provenance_and_abstention(self):
        result = self.run_cli("demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("synthetic", result.stdout)
        self.assertIn("Stored resolution:", result.stdout)
        self.assertIn("No suggestion:", result.stdout)
        self.assertIn("not a confidence percentage", result.stdout)
        for identifier in ("NT-1", "NT-2", "NT-3", "NT-4"):
            self.assertIn(f"Incoming {identifier}", result.stdout)
        self.assertIn("Resolved date: not supplied", result.stdout)
        self.assertIn("Created: 2025-", result.stdout)

    def test_supplied_batch_json_preserves_incoming_ids_and_source_dates(self):
        result = self.run_cli("batch", "--input", "data/new_tickets_example.json", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)["new_tickets"]
        self.assertEqual([row["ticket_id"] for row in rows], ["NT-1", "NT-2", "NT-3", "NT-4"])
        self.assertEqual(rows[0]["suggestions"]["results"], [])
        self.assertEqual(rows[1]["suggestions"]["results"][0]["ticket"]["id"], "T-1201")
        self.assertEqual(rows[2]["suggestions"]["results"][0]["ticket"]["id"], "T-1303")
        for row in rows:
            for match in row["suggestions"]["results"]:
                self.assertIsNone(match["ticket"]["resolved_at"])
                self.assertTrue(match["ticket"]["created_at"].startswith("2025-"))

    def test_category_filter(self):
        result = self.run_cli("search", "--title", "Revenue chart blank dashboard", "--category", "render", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        matches = json.loads(result.stdout)["results"]
        self.assertTrue(matches)
        self.assertTrue(all(match["ticket"]["category"] == "render" for match in matches))

    def test_batch_rejects_invalid_envelopes_and_duplicate_ids(self):
        incoming = {"ticket_id": "NT-X", "subject": "Blank revenue chart", "description": "No bars appear."}
        for payload in ([], {"new_tickets": []}, {"new_tickets": [incoming, incoming]}, {"new_tickets": [{"subject": "no id"}]}):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "incoming.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                result = self.run_cli("batch", "--input", str(path), "--json")
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)

    def test_invalid_limit_has_clean_error(self):
        result = self.run_cli("search", "--title", "SAML expired", "--limit", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("limit", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_dataset_has_clean_error(self):
        result = self.run_cli("search", "--title", "SAML expired", "--data", "does-not-exist.json")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_port_has_clean_error(self):
        result = self.run_cli("serve", "--port", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("port", result.stderr)

    def test_data_and_tenant_overrides(self):
        records = [{
            "id": "CUSTOM-1", "tenant_id": "custom", "title": "SAML certificate expired",
            "description": "SSO authentication failed after the signing certificate expired.",
            "product": "Identity", "status": "resolved", "resolution": "Rotate certificate.",
            "resolved_at": "2026-10-01",
        }]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tickets.json"
            path.write_text(json.dumps(records), encoding="utf-8")
            result = self.run_cli("search", "--title", "SAML certificate expired", "--data", str(path), "--tenant", "custom", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["results"][0]["ticket"]["id"], "CUSTOM-1")


if __name__ == "__main__":
    unittest.main()
