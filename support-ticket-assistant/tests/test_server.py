"""Integration tests use the real search engine through a loopback HTTP socket."""

import contextlib
import http.client
import io
import json
from pathlib import Path
import threading
import unittest

from ticket_assistant.engine import SearchEngine, load_tickets
from ticket_assistant.server import MAX_BODY_BYTES, make_server


def ticket(ticket_id, tenant, *, status="resolved"):
    return {
        "id": ticket_id,
        "tenant_id": tenant,
        "title": "SAML certificate expired",
        "description": "SSO authentication failed after signing certificate expiry.",
        "product": "Identity",
        "status": status,
        "resolution": "Replace the expired signing certificate and refresh SAML metadata." if status == "resolved" else "",
        "resolved_at": "2026-10-01" if status == "resolved" else None,
    }


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = SearchEngine([
            ticket("LOCAL-1", "solari-demo"),
            ticket("SECRET-1", "other-tenant"),
            ticket("OPEN-1", "solari-demo", status="open"),
        ], tenant_id="solari-demo")
        cls.server = make_server(engine, port=0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method="POST", path="/suggest", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), json.loads(response.read())
        finally:
            connection.close()

    def post(self, payload):
        return self.request(body=json.dumps(payload), headers={"Content-Type": "application/json"})

    def raw_request(self, headers, body=b""):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.putrequest("POST", "/suggest")
            for key, value in headers:
                connection.putheader(key, value)
            connection.endheaders(body)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_health_and_loopback_binding(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        status, headers, payload = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok", "mode": "local-demo"})
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_search_returns_only_scoped_resolved_ticket(self):
        status, _, payload = self.post({"title": "SAML certificate expired"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["reason"], "matches")
        self.assertEqual([m["ticket"]["id"] for m in payload["results"]], ["LOCAL-1"])
        self.assertNotIn("SECRET", json.dumps(payload))
        self.assertNotIn("OPEN-1", json.dumps(payload))

    def test_no_match_is_successful_empty_result(self):
        status, _, payload = self.post({"title": "Espresso grinder burr calibration"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"], [])

    def test_request_cannot_override_tenant(self):
        status, _, payload = self.post({"title": "SAML certificate expired", "tenant_id": "other-tenant"})
        self.assertEqual(status, 400)
        self.assertIn("Unsupported fields", payload["error"])

    def test_native_payload_normalizes_and_excludes_own_id(self):
        status, _, payload = self.post({"ticket_id": "NT-X", "subject": "SAML certificate expired", "category": "Identity"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["incoming_ticket_id"], "NT-X")
        self.assertEqual(payload["results"][0]["ticket"]["id"], "LOCAL-1")
        status, _, payload = self.post({"ticket_id": "LOCAL-1", "subject": "SAML certificate expired"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["results"], [])

    def test_native_and_canonical_fields_cannot_be_mixed(self):
        for payload in (
            {"ticket_id": "NT-X", "subject": "SAML certificate", "title": "other"},
            {"ticket_id": "NT-X", "subject": "SAML certificate", "exclude_ticket_id": "LOCAL-1"},
            {"ticket_id": "NT-X", "subject": "SAML certificate", "product": "Identity"},
            {"title": "SAML certificate", "category": "Identity", "product": "Identity"},
            {"subject": "SAML certificate"}, {"ticket_id": None, "subject": "SAML certificate"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload)[0], 400)

    def test_parameter_validation(self):
        for payload in (
            [], {"title": ""}, {"title": "   "}, {"title": 123},
            {"title": "x" * 301}, {"title": "test", "description": []},
            {"title": "test", "description": "x" * 10001},
            {"title": "test", "description": "x" * 10000},
            {"title": "test", "limit": True}, {"title": "test", "limit": 0},
            {"title": "test", "limit": 11}, {"title": "test", "product": []},
            {"title": "test", "product": " "}, {"title": "test", "exclude_ticket_id": 5},
        ):
            with self.subTest(payload=str(payload)[:100]):
                self.assertEqual(self.post(payload)[0], 400)

    def test_invalid_json_unicode_and_duplicate_fields(self):
        for body in (b"{", b"\xff", b'{"title":"first","title":"second"}', b'{"ticket_id":"\\ud800","subject":"password reset"}'):
            with self.subTest(body=body):
                self.assertEqual(self.request(body=body, headers={"Content-Type": "application/json"})[0], 400)

    def test_content_type(self):
        self.assertEqual(self.request(body='{"title":"SAML"}', headers={"Content-Type": "text/plain"})[0], 415)

    def test_content_length_validation(self):
        content_type = ("Content-Type", "application/json")
        for length in ("-1", "no", "1, 1"):
            with self.subTest(length=length):
                self.assertEqual(self.raw_request([content_type, ("Content-Length", length)])[0], 400)
        self.assertEqual(self.raw_request([content_type])[0], 411)
        self.assertEqual(self.raw_request([content_type, ("Content-Length", "2"), ("Content-Length", "2")], b"{}")[0], 400)
        self.assertEqual(self.raw_request([content_type, ("Content-Length", str(MAX_BODY_BYTES + 1))])[0], 413)
        self.assertEqual(self.raw_request([content_type, ("Content-Length", "9" * 5000)])[0], 413)
        self.assertEqual(self.raw_request([content_type, ("Transfer-Encoding", "chunked")])[0], 400)

    def test_unknown_route(self):
        self.assertEqual(self.request("GET", "/")[0], 404)
        self.assertEqual(self.request("POST", "/new-ticket")[0], 404)

    def test_foreign_host_and_origin_blocked(self):
        body = '{"title":"SAML certificate expired"}'
        for header in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}):
            self.assertEqual(self.request(body=body, headers={"Content-Type": "application/json", **header})[0], 403)

    def test_query_content_not_logged(self):
        capture = io.StringIO()
        with contextlib.redirect_stderr(capture):
            self.post({"title": "SAML certificate expired", "description": "PRIVATE_MARKER"})
            self.request("GET", "/?PRIVATE_MARKER")
        self.assertNotIn("PRIVATE_MARKER", capture.getvalue())


class SuppliedSeedApiTests(unittest.TestCase):
    def test_all_native_provider_examples_run_with_preserved_metadata(self):
        root = Path(__file__).resolve().parents[1]
        engine = SearchEngine(load_tickets(root / "data" / "tickets.json"), tenant_id="solari-seed")
        incoming = json.loads((root / "data" / "new_tickets_example.json").read_text(encoding="utf-8"))["new_tickets"]
        server = make_server(engine, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for ticket in incoming:
                connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
                try:
                    connection.request("POST", "/suggest", body=json.dumps(ticket), headers={"Content-Type": "application/json"})
                    response = connection.getresponse()
                    payload = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertEqual(payload["incoming_ticket_id"], ticket["ticket_id"])
                    for match in payload["results"]:
                        self.assertTrue(match["ticket"]["id"].startswith("T-"))
                        self.assertEqual(match["ticket"]["tenant_id"], "solari-seed")
                        self.assertIsNone(match["ticket"]["resolved_at"])
                        self.assertTrue(match["ticket"]["created_at"].startswith("2025-"))
                finally:
                    connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
