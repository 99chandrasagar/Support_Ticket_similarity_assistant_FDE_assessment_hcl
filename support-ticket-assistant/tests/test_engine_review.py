"""Regression checks for failures discovered during the panel demo review."""

import unittest

from ticket_assistant.engine import SearchEngine


class BoilerplateMatchRegressionTests(unittest.TestCase):
    def test_temporal_boilerplate_does_not_make_a_shared_product_a_match(self):
        ticket = {
            "id": "SAML-LOOP",
            "tenant_id": "solari-demo",
            "title": "SAML redirect loop after configuration change",
            "description": "The assertion audience differs from the configured entity identifier.",
            "product": "Identity",
            "status": "resolved",
            "resolution": "Corrected the assertion audience and verified login.",
            "resolved_at": "2026-10-09",
        }
        engine = SearchEngine([ticket], tenant_id="solari-demo")

        # The old gate admitted this ticket because both "saml" and "after"
        # overlapped. A temporal preposition provides no evidence that a redirect
        # configuration fix addresses an expired certificate.
        result = engine.search("SAML certificate expired after renewal")

        self.assertEqual(result["reason"], "no_match")
        self.assertEqual(result["results"], [])

    def test_specific_symptoms_still_retrieve_a_relevant_source(self):
        ticket = {
            "id": "SAML-CERT",
            "tenant_id": "solari-demo",
            "title": "SAML certificate expired",
            "description": "The signing certificate expired during login.",
            "product": "Identity",
            "status": "resolved",
            "resolution": "Renewed the signing certificate and verified login.",
            "resolved_at": "2026-10-15",
        }

        result = SearchEngine([ticket], "solari-demo").search(
            "SAML certificate expired after renewal"
        )

        self.assertEqual(result["reason"], "matches")
        self.assertEqual(result["results"][0]["ticket"]["id"], "SAML-CERT")


if __name__ == "__main__":
    unittest.main()
