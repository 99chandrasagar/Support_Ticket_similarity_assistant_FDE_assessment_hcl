"""Identical-template synthetic stress check, not a production benchmark."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import platform
import statistics
import time

from ticket_assistant.engine import SearchEngine, load_tickets


ROOT = Path(__file__).resolve().parent
TENANT = "solari-seed"
QUERY_IDS = ("NT-1", "NT-2", "NT-3")


def _summarize_ms(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "samples": len(samples),
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 3),
    }


def benchmark(records: int = 55_000, queries: int = 60) -> dict:
    if records < 1:
        raise ValueError("records must be at least 1.")
    if queries < len(QUERY_IDS):
        raise ValueError(f"queries must be at least {len(QUERY_IDS)} to exercise every query template.")
    source = load_tickets(ROOT / "data" / "tickets.json")
    templates = [
        record for record in source
        if record["tenant_id"] == TENANT
        and record["status"] == "resolved"
        and record["resolution"].strip()
    ]
    if not templates:
        raise ValueError("The bundled fixture contains no eligible ticket templates.")
    fixture = json.loads((ROOT / "data" / "new_tickets_example.json").read_text(encoding="utf-8"))
    by_id = {query["ticket_id"]: query for query in fixture["new_tickets"]}
    query_templates = [by_id[identifier] for identifier in QUERY_IDS]
    for query in query_templates:
        if not isinstance(query["subject"], str) or not isinstance(query["description"], str):
            raise ValueError("Supplied incoming tickets require string subject and description.")

    # Deliberately duplicate text, changing only record IDs. This creates a
    # reproducible, artificial posting-list workload, not new customer history.
    expanded = [
        {**templates[index % len(templates)], "id": f"BENCH-{index + 1:08d}"}
        for index in range(records)
    ]
    started = time.perf_counter()
    engine = SearchEngine(expanded, tenant_id=TENANT)
    build_ms = (time.perf_counter() - started) * 1000
    # The timed build includes the engine's validation and tokenization of all
    # expanded records; file loading and template replication are outside it.
    del expanded

    for query in query_templates:
        engine.search(query["subject"], query["description"], limit=3)

    timings: list[float] = []
    per_query: dict[str, list[float]] = {identifier: [] for identifier in QUERY_IDS}
    result_counts: dict[str, int] = {}
    for index in range(queries):
        query = query_templates[index % len(query_templates)]
        started = time.perf_counter()
        response = engine.search(query["subject"], query["description"], limit=3)
        elapsed_ms = (time.perf_counter() - started) * 1000
        timings.append(elapsed_ms)
        per_query[query["ticket_id"]].append(elapsed_ms)
        result_counts[query["ticket_id"]] = len(response["results"])

    return {
        "provenance": "Identical-template synthetic stress check. The assessment's eligible synthetic seed tickets are repeated with unique IDs. This is not a production benchmark or an estimate of performance on a real corpus.",
        "environment": {"python": platform.python_version(), "platform": platform.system(), "architecture": platform.machine()},
        "scope": {
            "records": records,
            "available_ticket_templates": len(templates),
            "distinct_ticket_templates_used": min(records, len(templates)),
            "query_template_ids": list(QUERY_IDS),
            "warmup_queries_excluded": len(query_templates),
            "timed_queries": queries,
            "result_limit": 3,
            "default_volume_rationale": "55,000 is a rounded one-year planning assumption at 150 incoming tickets per day; here all replicated records are treated as eligible resolved history.",
        },
        "timing": {
            "index_build_ms": round(build_ms, 3),
            "index_build_scope": "SearchEngine construction, including validation and tokenization; excludes disk reads and fixture replication.",
            "search_scope": "Warm sequential in-process search. Includes ranking and result construction; excludes HTTP, concurrency, process startup and network. p95 uses the nearest-rank method.",
            **_summarize_ms(timings),
        },
        "query_timings": {
            identifier: {**_summarize_ms(samples), "returned_results": result_counts[identifier]}
            for identifier, samples in per_query.items()
        },
        "limitations": [
            "Identical text repetition changes term frequencies and posting-list lengths artificially; it does not represent vocabulary diversity or real relevance.",
            "Only the supplied NT-1, NT-2 and NT-3 queries are exercised; this is a performance stress check, not retrieval-quality evaluation. Some queries can correctly produce no suggestion.",
            "Single local process, sequential requests, one timing run; no production latency, throughput, availability or memory claim.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=55_000, help="Replicated eligible records (default: 55000)")
    parser.add_argument("--queries", type=int, default=60, help="Total timed searches, cycling three query templates (default: 60)")
    parser.add_argument("--json", action="store_true", help="Print the complete machine-readable report")
    args = parser.parse_args()
    try:
        report = benchmark(args.records, args.queries)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, indent=2, allow_nan=False))
    else:
        timing = report["timing"]
        scope = report["scope"]
        print(report["provenance"])
        print(f"\nRecords: {scope['records']:,}; distinct ticket templates: {scope['distinct_ticket_templates_used']}; timed searches: {scope['timed_queries']}.")
        print(f"Index build: {timing['index_build_ms']:.3f} ms")
        print(f"Warm search median: {timing['median_ms']:.3f} ms; p95: {timing['p95_ms']:.3f} ms")
        print(timing["index_build_scope"])
        print(timing["search_scope"])
        for identifier, result in report["query_timings"].items():
            print(f"{identifier}: {result['samples']} searches; median {result['median_ms']:.3f} ms; p95 {result['p95_ms']:.3f} ms; {result['returned_results']} results")
        for limitation in report["limitations"]:
            print(f"Limitation: {limitation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
