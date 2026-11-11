# Support Ticket Similarity Assistant

## Recommendation and customer outcome

Solari Analytics receives about 150 support tickets daily. Agents need to find relevant previous fixes quickly and answer consistently. I propose a retrieval assistant that shows up to three resolved cases by default, with their source IDs, original descriptions, recorded resolutions, and matching terms. The agent checks whether the prior fix applies. The assistant does not generate answers, change customer accounts, or send responses.

The implementation runs against the 40 historical tickets and four incoming examples supplied in the starter kit. A CLI, batch command, and local HTTP endpoint share one retrieval engine. The provider's synthetic JSON files are preserved unchanged.

## Assumptions and discovery

"Similar" means a previous case has symptoms or technical terms worth investigating. Topic similarity does not prove the same cause. I assume English text and that agents may search the supplied synthetic support corpus. The data contains categories, tags, creation dates, and resolved status, but no customer identity, agent permissions, or resolution timestamps. The import assigns a dataset namespace, not an inferred customer identity; missing resolution dates stay unknown. This dataset cannot establish customer isolation in a real deployment.

For planning, twelve months at 150 arrivals every calendar day is about 55,000 records. I would confirm actual history, peak traffic, retention, permissions, and whether cross-customer fixes can be shared in sanitized form. I would ask the support lead to distinguish useful related cases from directly applicable fixes and label both before setting quality thresholds.

## Architecture and matching

```text
Supplied JSON -> validate and normalize -> eligible history -> in-memory index
                                                               |
Incoming ticket -> CLI or local API -> tokenize -> retrieve and rank
                                                               |
                                source cases and recorded fixes
```

The importer maps the starter schema without changing the source files. Only resolved records with nonblank resolutions contribute to the index. BM25 ranks the title repeated twice plus the description; resolution notes and tags are excluded from retrieval because their availability at ticket creation is unknown. Optional exact category filtering and source-ticket exclusion constrain candidates. An inverted index limits scoring to records sharing query terms, with deterministic tie-breaking.

The evidence gate requires at least two distinct matching terms and 25% query-term coverage, or an exact distinctive error identifier. It can return no suggestions. Ranking scores are relative values, not confidence percentages. These explicit heuristics need real relevance labels; long descriptions, paraphrases, negation, and shared generic vocabulary remain weaknesses.

The provided keyword-overlap helper is retained for reference. It has no stop-word filtering or eligibility gate and returns top candidates even when overlap is zero. The replacement adds these controls and validation. BM25 is an inspectable, inexpensive baseline; the [Elastic reference](https://www.elastic.co/docs/reference/elasticsearch/index-settings/similarity) describes its frequency and length controls. There is no Elasticsearch dependency. I would add hybrid lexical and embedding retrieval only if independently labeled errors demonstrate enough benefit to justify model, privacy, latency, and operational costs.

## Behavior and deployment boundaries

The four provided examples are part of the demo. Blank revenue charts and duplicate billing have directly relevant history. The password-reset email example has related login history but no exact email-delivery fix; a related result must not be represented as a diagnosis. The Snowflake example is intentionally outside known history and should receive no strong suggestion. `VALIDATION.md` records actual outputs and retained failures.

Invalid input produces a clear error. Empty or weak evidence yields no suggestions. Source text and recorded dates support agent review. The index is a startup snapshot, requiring restart after history changes. The local endpoint demonstrates the integration boundary; no live webhook, agent UI, ticket persistence, or identity system is implemented. It binds to loopback, does not log ticket bodies, and makes no external AI calls. Python [documents the HTTP server's production limitations](https://docs.python.org/3.12/library/http.server.html).

## Validation and next steps

All 65 functional tests pass. Evaluation distinguishes provider examples from authored relevance labels: the chart example has a weak secondary suggestion, and an authored browser-extension negative retrieves the wrong chart fix. The artificial 55,000-record check records 544 ms p95 in-process search, above the proposed 500 ms end-to-end target. This exposes performance work before a pilot; repeated seed text cannot establish real-world capacity.

Before a pilot, obtain permission-scoped history and independent, time-separated relevance labels, using only cases resolved before each query. Measure useful suggestions, harmful recommendations, coverage, and agent lookup time against a baseline. Integrate authenticated helpdesk events with versioned, idempotent updates and reopen/delete handling; outages must not block ticket creation. Benchmark representative bursts against a proposed 500 ms p95 end-to-end target. Move to a persistent index or hybrid retrieval when measured quality or resource limits justify it, with authentication, authorization, privacy controls, and monitoring before deployment.
