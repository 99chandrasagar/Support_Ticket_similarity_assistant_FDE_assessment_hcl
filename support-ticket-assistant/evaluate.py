"""Evaluate supplied synthetic history and untouched incoming examples.

Relevance judgments are locally authored development checks, not a provider
answer key, an independent benchmark, or certification of a reusable fix.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

from ticket_assistant.engine import SearchEngine, load_tickets


ROOT = Path(__file__).resolve().parent


def evaluate_provided_examples(engine: SearchEngine, examples_path: Path) -> dict:
    """Keep supplied input text intact and distinguish related cases from fixes."""
    with examples_path.open(encoding="utf-8") as handle:
        examples = json.load(handle)["new_tickets"]
    judgments = {
        "NT-1": {
            "relevant_ids": [], "related_ids": ["T-1001"],
            "expected_behavior": "No exact delivery fix is present; abstain under the strict relevance policy. T-1001 can at most be adjacent investigation context.",
            "assessment_note": "NT-1 says the reset email never arrives. T-1001 assumes the reset email arrived and a password was rejected due to letter case. Its copy-paste advice does not resolve email delivery.",
        },
        "NT-2": {
            "relevant_ids": ["T-1201"], "related_ids": [],
            "expected_behavior": "Surface T-1201 as a useful historical comparison; confirm the current filter and row count before reusing the empty-data explanation.",
            "assessment_note": "A blank revenue chart with no bars resembles T-1201, but the incoming example does not establish the current root cause.",
        },
        "NT-3": {
            "relevant_ids": ["T-1303"], "related_ids": [],
            "expected_behavior": "Surface T-1303 as a useful historical comparison; verify the payment records before attributing the duplicate to retries.",
            "assessment_note": "Two charges in one billing cycle resemble T-1303. The similarity result does not authorize a refund or prove the retry mechanism caused this incident.",
        },
        "NT-4": {
            "relevant_ids": [], "related_ids": [],
            "expected_behavior": "Abstain from a strong match because the history contains no Snowflake connection incident; investigate the new connector.",
            "assessment_note": "Salesforce and HubSpot authentication fixes must not be treated as a Snowflake fix solely because all mention integration or sync.",
        },
    }
    if not isinstance(examples, list) or len(examples) != 4 or any(not isinstance(item, dict) for item in examples) or {item.get("ticket_id") for item in examples} != set(judgments):
        raise ValueError("Provided example file must contain NT-1 through NT-4 exactly once.")
    rows = []
    for example in examples:
        judgment = judgments[example["ticket_id"]]
        response = engine.search(example["subject"], example["description"], limit=3)
        ids = [item["ticket"]["id"] for item in response["results"]]
        relevant = set(judgment["relevant_ids"])
        rank = next((i for i, identifier in enumerate(ids, 1) if identifier in relevant), None)
        rows.append({
            "id": example["ticket_id"], "input": dict(example),
            **judgment, "returned_ids": ids, "first_relevant_rank": rank,
            "unlabeled_returned_ids": [identifier for identifier in ids if identifier not in relevant],
            "reason": response["reason"],
            "passed": rank is not None if relevant else not ids,
        })
    known = [row for row in rows if row["relevant_ids"]]
    unknown = [row for row in rows if not row["relevant_ids"]]
    total_known_returned = sum(len(row["returned_ids"]) for row in known)
    labeled_known_returned = sum(sum(identifier in row["relevant_ids"] for identifier in row["returned_ids"]) for row in known)
    return {
        "provenance": "All four incoming inputs are read verbatim from the provider's new_tickets_example.json. Expected behavior and relevance judgments are locally authored; the provider did not supply a gold answer key.",
        "policy": "Known-source examples require a labeled historical comparison in the top three. No-exact-source examples require abstention under this deliberately strict relevance policy; related vocabulary alone is insufficient. These results are separate from authored-query metrics.",
        "metrics": {
            "known_source_examples": len(known),
            "known_source_hits_at_3": sum(row["first_relevant_rank"] is not None for row in known),
            "labeled_known_source_suggestions": labeled_known_returned,
            "total_known_source_suggestions": total_known_returned,
            "labeled_suggestion_precision_on_known_examples": labeled_known_returned / total_known_returned if total_known_returned else None,
            "no_exact_source_examples": len(unknown),
            "no_exact_source_false_suggestions": sum(bool(row["returned_ids"]) for row in unknown),
        },
        "cases": rows,
    }


def evaluate(data_path: Path, queries_path: Path, repeats: int = 20, examples_path: Path = ROOT / "data" / "new_tickets_example.json") -> dict:
    tickets = load_tickets(data_path)
    with queries_path.open(encoding="utf-8") as handle:
        fixture = json.load(handle)
    tenant = fixture["tenant_id"]
    queries = fixture["queries"]
    if not queries or repeats < 1:
        raise ValueError("At least one query and one timing repeat are required.")
    valid_ids = {ticket["id"] for ticket in tickets if ticket["tenant_id"] == tenant and ticket["status"] == "resolved" and ticket["resolution"].strip()}
    for query in queries:
        if not set(query["relevant_ids"]).issubset(valid_ids):
            raise ValueError(f"Query {query['id']} labels missing or ineligible tickets.")
    started = time.perf_counter()
    engine = SearchEngine(tickets, tenant)
    build_ms = (time.perf_counter() - started) * 1000
    rows = []
    positive_hits = 0
    reciprocal_ranks = []
    false_suggestions = 0
    positive_count = 0
    negative_count = 0
    labeled_relevant_returned = 0
    total_returned_on_positives = 0
    for query in queries:
        response = engine.search(query["title"], query.get("description", ""), limit=3)
        ids = [item["ticket"]["id"] for item in response["results"]]
        relevant = set(query["relevant_ids"])
        rank = next((i for i, identifier in enumerate(ids, 1) if identifier in relevant), None)
        if relevant:
            positive_count += 1
            positive_hits += int(rank is not None)
            reciprocal_ranks.append(1 / rank if rank is not None else 0)
            labeled_relevant_returned += sum(identifier in relevant for identifier in ids)
            total_returned_on_positives += len(ids)
        else:
            negative_count += 1
            false_suggestions += int(bool(ids))
        rows.append({
            "id": query["id"], "kind": "positive" if relevant else "negative",
            "relevant_ids": query["relevant_ids"], "returned_ids": ids,
            "first_relevant_rank": rank, "reason": response["reason"],
            "passed": rank is not None if relevant else not ids,
            "label_note": query.get("label_note", "One labeled historical root cause; other returned tickets count as unlabeled for precision." if relevant else "No relevant history record is labeled for this query."),
        })

    # Warm index timing includes Python search only, excluding HTTP, process
    # startup, dataset loading and network. Each query is measured equally.
    timings = []
    for _ in range(repeats):
        for query in queries:
            started = time.perf_counter()
            engine.search(query["title"], query.get("description", ""), limit=3)
            timings.append((time.perf_counter() - started) * 1000)
    ordered = sorted(timings)
    return {
        "provenance": fixture["provenance"],
        "label_policy": fixture.get("label_policy", "Locally authored relevance judgments."),
        "environment": {"python": platform.python_version(), "platform": platform.system()},
        "scope": {"tenant_id": tenant, "history_records": len(tickets), "eligible_records": len(valid_ids), "positive_queries": positive_count, "negative_queries": negative_count},
        "metrics": {
            "hit_at_3": positive_hits / positive_count if positive_count else None,
            "mrr_at_3": statistics.mean(reciprocal_ranks) if reciprocal_ranks else None,
            "false_suggestion_rate": false_suggestions / negative_count if negative_count else None,
            "positive_hits": positive_hits, "negative_false_suggestions": false_suggestions,
            "labeled_suggestion_precision_on_positives": labeled_relevant_returned / total_returned_on_positives if total_returned_on_positives else None,
            "labeled_relevant_returned_on_positives": labeled_relevant_returned,
            "total_returned_on_positives": total_returned_on_positives,
        },
        "metric_notes": {
            "hit_at_3": "Fraction of positive queries with at least one labeled relevant ticket in the first three results. It does not penalize additional irrelevant results.",
            "mrr_at_3": "Mean reciprocal rank of the first labeled relevant result, with zero for a miss.",
            "labeled_suggestion_precision_on_positives": "Total labeled relevant returned divided by total returned across positive queries. Unlabeled candidates count as irrelevant; labels are synthetic and not independently adjudicated.",
            "false_suggestion_rate": "Fraction of authored negative queries with any returned suggestion, including in-domain clock-skew and browser-extension cases. Failure cases are retained, not tuned away.",
        },
        "timing": {
            "scope": "Warm in-process retrieval only; excludes file loading, process startup, HTTP and network; tiny synthetic corpus is not a scale benchmark.",
            "samples": len(timings), "index_build_ms": round(build_ms, 3),
            "median_ms": round(statistics.median(timings), 3),
            "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 3),
        },
        "cases": rows,
        "provided_examples": evaluate_provided_examples(engine, examples_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "tickets.json")
    parser.add_argument("--queries", type=Path, default=ROOT / "data" / "evaluation_queries.json")
    parser.add_argument("--examples", type=Path, default=ROOT / "data" / "new_tickets_example.json")
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Print full machine-readable results.")
    args = parser.parse_args()
    try:
        report = evaluate(args.data, args.queries, args.repeats, args.examples)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(report["provenance"])
        scope = report["scope"]
        metrics = report["metrics"]
        def percent(value):
            return f"{value:.1%}" if value is not None else "not applicable"
        print(f"\nHistory: {scope['history_records']} records; {scope['eligible_records']} eligible for {scope['tenant_id']}.")
        print(f"Hit@3: {metrics['positive_hits']}/{scope['positive_queries']} ({percent(metrics['hit_at_3'])})")
        print(f"MRR@3: {metrics['mrr_at_3']:.3f}" if metrics['mrr_at_3'] is not None else "MRR@3: not applicable")
        print(f"Labeled suggestion precision on positives: {metrics['labeled_relevant_returned_on_positives']}/{metrics['total_returned_on_positives']} ({percent(metrics['labeled_suggestion_precision_on_positives'])})")
        print(f"False suggestions: {metrics['negative_false_suggestions']}/{scope['negative_queries']} ({percent(metrics['false_suggestion_rate'])})")
        for row in report["cases"]:
            print(f"  {row['id']} {'PASS' if row['passed'] else 'FAIL'}: {', '.join(row['returned_ids']) or '(abstained)'}")
        print("\nSupplied examples (unchanged inputs; locally authored relevance judgments):")
        for row in report["provided_examples"]["cases"]:
            print(f"  {row['id']} {'PASS' if row['passed'] else 'REVIEW'}: {', '.join(row['returned_ids']) or '(abstained)'}")
            print(f"    {row['assessment_note']}")
            if row["unlabeled_returned_ids"]:
                print(f"    Unlabeled candidates requiring caution: {', '.join(row['unlabeled_returned_ids'])}")
        provided_metrics = report["provided_examples"]["metrics"]
        print(f"Supplied known-source suggestion precision: {provided_metrics['labeled_known_source_suggestions']}/{provided_metrics['total_known_source_suggestions']} ({percent(provided_metrics['labeled_suggestion_precision_on_known_examples'])})")
        timing = report["timing"]
        print(f"\nWarm retrieval: median {timing['median_ms']:.3f} ms; p95 {timing['p95_ms']:.3f} ms over {timing['samples']} calls.")
        print(timing["scope"])
    return 0 if all(row["passed"] for row in report["cases"] + report["provided_examples"]["cases"]) else 1


if __name__ == "__main__":
    sys.exit(main())
