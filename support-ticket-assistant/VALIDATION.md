# Support Ticket Similarity Assistant validation

Recorded on 11 November 2026 using Python 3.12.14 on Windows. The default inputs are the assessment provider's synthetic seed files. Relevance labels and adversarial fixtures are locally authored. No live helpdesk, customer data, independent relevance benchmark, or production service was tested.

## Functional checks and source integrity

```shell
python -m unittest discover -s tests -q
```

**65 tests passed.** Checks cover native seed import, input validation, duplicate IDs, metadata preservation, immutable source/results, exact category filtering, self-exclusion, resolved-only eligibility, and deterministic ranking. The CLI and batch tests execute real subprocesses; API tests make real loopback HTTP requests. Transport checks include malformed JSON and Unicode, duplicate fields/headers, limits, fixed scope, Host/Origin restrictions, and query-log privacy.

The two supplied data files, original utility, and starter README remain byte-for-byte identical to the extracted starter package. See `data/README.md` for data hashes. The default history has 40 eligible records. Separate test fixtures exercise multiple tenants; the supplied data has no customer identity and cannot establish real customer isolation.

Creation dates remain source creation dates. No resolution timestamps are fabricated. Only Windows/Python 3.12.14 was executed; Python 3.11+ is the intended requirement, with other versions and platforms untested.

## Four supplied incoming examples

```shell
python -m ticket_assistant demo
python -m ticket_assistant batch --input data/new_tickets_example.json --json
```

| Supplied example | Actual result | Assessment |
| --- | --- | --- |
| NT-1 Missing reset email | No suggestion | No exact delivery-resolution source exists. T-1001 assumes the email arrived and concerns a rejected password. |
| NT-2 Blank revenue chart | T-1201, then T-1501 | The first source is useful. The second concerns missing permissions and is not labeled relevant. |
| NT-3 Duplicate charge | T-1303 | Useful historical comparison; current payment evidence still needs verification. |
| NT-4 Snowflake connection | No suggestion | No strong Snowflake source exists; generic integration fixes are not substituted. |

The two examples with known useful sources both retrieve them first. Of the three suggestions returned across those examples, two are labeled relevant: **2/3 or 66.7%**. The two no-exact-source examples both abstain. These judgments are local interpretations, not a provider answer key. Passing the example-level hit/abstention checks does not make every returned candidate correct.

## Locally authored relevance checks

```shell
python evaluate.py --json
```

| Measure | Recorded result |
| --- | --- |
| Positive queries with a labeled source in the top three | 12 of 12 |
| Reciprocal rank at three on positives | 1.000 |
| Labeled relevant suggestions on positives | 12 of 12 returned |
| Negative queries producing any suggestion | 1 of 6 or 16.7% |
| Warm search median on the 40-record corpus | 0.165 ms |
| Warm search p95 on the 40-record corpus | 0.267 ms |
| Engine index build on the 40-record corpus | 4.396 ms |
| Timed searches | 360 |

The complete report is `verification/evaluation.json`. Positive-query success is not an overall accuracy estimate: the queries were authored after reviewing the supplied history, the sample is small, and there is no independent adjudication. Unlabeled suggestions count as irrelevant under the declared root-cause policy. Provider examples are reported separately rather than folded into these numbers.

**Retained failure N06:** a blank revenue chart is explicitly attributed to a browser extension, while the query rules out empty data. The engine still suggests T-1201, whose historical cause is an empty query result. Shared vocabulary does not establish the cause, and this lexical baseline does not understand the exclusion. The clock-skew negative now abstains on this different history; no labels were changed to conceal an observed failure.

The evaluator completes with **exit code 1** because of N06. Exit 0 requires every positive to retrieve a labeled source in the first three and every negative to abstain, including the separately assessed provider examples. Exit 2 denotes argument or input errors. Suggestion precision is descriptive and not part of the exit-code gate.

The small-corpus timing includes only warm in-process search, excluding startup, file loading, HTTP, and network. It varies with desktop load and does not establish production latency.

## Artificial volume check

```shell
python benchmark.py --records 55000 --queries 60 --json
```

The recorded report is `verification/benchmark.json`.

| Measure | Recorded result |
| --- | --- |
| History | 55,000 records copied from 40 supplied templates with unique IDs |
| Queries | NT-1, NT-2, NT-3 cycled over 60 sequential searches |
| Warmups excluded | Three |
| Index build | 4,009.197 ms |
| Warm search median | 188.048 ms |
| Warm search p95 | 544.265 ms |

Index build includes validation and tokenization but excludes fixture replication and disk reads. Search includes ranking and result construction but excludes HTTP, concurrency, startup, and network. p95 uses the nearest-rank method. The run used Windows AMD64 on a shared desktop; there is no isolated-hardware, throughput, memory, or availability claim.

**The observed 544 ms p95 exceeds the proposed 500 ms end-to-end target even before HTTP overhead.** This prototype has not met that target at the artificial volume. Repeated text inflates posting lists and changes term statistics; it does not represent realistic vocabulary diversity. Repeated variants also occupy multiple result slots, so this check is not a relevance evaluation.

Before a pilot, profile common-term queries, reduce work spent constructing and sorting candidates that will not appear in the top results, and test a persistent index if needed. Then rerun representative history and burst traffic with end-to-end timing. Keep the declared quality failures in the evaluation while testing any ranking or performance changes.
