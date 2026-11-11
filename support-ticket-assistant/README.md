# Support Ticket Similarity Assistant

A runnable response to the Solari Analytics case. Submit an incoming ticket and inspect similar resolved cases, their recorded fixes, and the terms that matched. The assistant can return no suggestions and never applies a fix automatically.

The default history and incoming examples are the **unchanged synthetic files supplied in the assessment starter kit**. Evaluation labels and adversarial test fixtures are locally authored and identified separately.

## Quick start

Requires Python 3.11 or newer. No third-party packages, API keys, model downloads, or installation steps.

Extract the archive, open a terminal inside `support-ticket-assistant`, and run:

```shell
python -m ticket_assistant demo
```

On Windows, use `py -3` if Python is installed through the launcher; on macOS or Linux, `python3` may be needed. All four supplied incoming tickets are processed:

| Incoming ticket | Observed result | How to interpret it |
| --- | --- | --- |
| NT-1 Password-reset email never arrives | No suggestion | T-1001 concerns a rejected password after receiving the reset email; it is not an email-delivery fix. |
| NT-2 Revenue chart is blank | T-1201 first; T-1501 second | T-1201 is a useful comparison. The permission-related secondary result is weaker and not labeled relevant. |
| NT-3 Charged twice | T-1303 first | Check payment evidence before assuming the same retry issue. |
| NT-4 Snowflake integration fails | No suggestion | No strong Snowflake history is present. |

Creation dates are displayed as creation dates. Resolution dates are unknown in the supplied data.

## Batch and individual queries

Run the supplied incoming file directly and produce JSON:

```shell
python -m ticket_assistant batch --input data/new_tickets_example.json --json
```

The response preserves each incoming `ticket_id` and `subject`, with a `suggestions` object for each. For an individual query:

```shell
python -m ticket_assistant search --title "Charged twice this month" --description "Two charges appear for a single monthly subscription." --category billing --json
```

Optional search controls include `--limit 3`, `--category billing`, and `--exclude-ticket-id T-1303`. Category values are case-sensitive. The supplied categories are `api`, `auth`, `billing`, `export`, `perf`, `perm`, `render`, and `sync`. Use `--help` after any subcommand.

## Local new-ticket API

Start the loopback-only service:

```shell
python -m ticket_assistant serve --port 8000
```

In a second terminal, from the project directory:

```shell
curl -H "Content-Type: application/json" --data-binary "@examples/new_ticket.json" http://127.0.0.1:8000/suggest
```

`examples/new_ticket.json` contains the supplied NT-2 record as a single request. In Windows PowerShell use `curl.exe`, or:

```powershell
$requestBody = Get-Content -Raw -LiteralPath .\examples\new_ticket.json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/suggest -ContentType 'application/json' -Body $requestBody | ConvertTo-Json -Depth 8
```

`GET /health` checks readiness. `POST /suggest` accepts the native incoming schema:

```json
{
  "ticket_id": "NT-3",
  "subject": "Getting charged twice this month",
  "description": "Customer's card statement shows two charges for a single subscription payment.",
  "category": "billing",
  "limit": 3
}
```

Native requests require `ticket_id` and `subject`; the other fields are optional. The ID excludes a source ticket with the same ID. It does not authenticate a customer or write a ticket.

The alternative canonical request accepts `title`, optional `description`, `category`, `exclude_ticket_id`, and `limit`. Do not mix native and canonical names. The internal `product` filter name remains a compatibility alias for category; do not specify both. Requests cannot override the process's dataset scope.

Responses contain `reason`, `results`, `query_terms`, and `total_eligible`. Native API responses also echo `incoming_ticket_id`. Reasons are `matches`, `no_match`, or `insufficient_query`. Each match includes the source ticket, ranking score, matching terms, and warnings. Scores are not confidence percentages.

Limits: 32 KiB request body, 300-character title/subject, 10,000 combined title and description characters, 100-character IDs/category, and 1-10 results. Invalid inputs return JSON errors. There is no browser UI at the root URL. Stop the server with Ctrl+C.

## Verification

```shell
python -m unittest discover -s tests -v
python evaluate.py
```

The functional tests check import, metadata preservation, filtering, retrieval, and real CLI/API behavior. Evaluation separately reports the four provider examples and locally authored positive/negative queries. It also reports extra incorrect suggestions, rather than relying only on successful top-three hits.

The evaluator currently completes with **exit code 1** because a retained hard negative produces an incorrect chart suggestion. This is a documented relevance limitation, not a crashed command. Exit 0 requires all case-level relevance checks to pass; exit 2 denotes invalid arguments/data. Precision is reported separately, not included in that exit-code gate. See `VALIDATION.md` and `verification/evaluation.json` for measured results.

Optional artificial volume check:

```shell
python benchmark.py --records 55000 --queries 60 --json
```

This replicates the 40 supplied records with unique IDs. It measures build and sequential in-process retrieval, not real-corpus relevance or production traffic.

## Data and import assumptions

`data/tickets.json` retains the original `{"tickets": [...]}` wrapper and fields: `ticket_id`, `subject`, `description`, `resolution_notes`, `category`, `tags`, `created_at`, and `status`. Source IDs, resolution text, categories, tags, and creation dates are preserved. Only resolved records with a nonblank resolution are eligible.

The adapter normalizes `ticket_id -> id`, `subject -> title`, and `resolution_notes -> resolution`; `category` also supplies the internal `product` filter. It keeps `created_at`, tags, source-schema metadata, and `resolved_at: null`. The fixed `solari-seed` namespace identifies this dataset. No customer identity or resolution date is invented. Source tags are retained for inspection but are not search features.

Use `--data path/to/tickets.json` after a subcommand for another file with the same schema. IDs must be unique, tags an array of strings, and dates valid ISO dates. Import validates the whole file and fails clearly on malformed data. The source wrapper must not contain customer tenant IDs: permission-scoped imports require an explicit mapping instead of silently replacing identity. Restart after changing history.

A legacy canonical array schema is also supported for isolated regression fixtures; `tests/fixtures/demo_tickets.json` demonstrates it. Its `--tenant` scope is an engine invariant, not production authentication. Those fixtures are not mixed into the supplied history.

## Retrieval and limitations

BM25 uses title text twice and description once, with `k1=1.5` and `b=0.75`. Resolution text and tags are not indexed. Tokenization lowercases ASCII terms, removes a documented stop list, and preserves identifiers such as `ERR_AUTH_401`. There is no stemming, synonym expansion, semantic model, or generative answer.

Candidates need two distinct shared terms covering at least 25% of informative query terms, or one exact alphanumeric identifier containing an underscore/hyphen. A plain numeric code such as `403` alone is insufficient. Results sort by unrounded score, then source ID. The gate is an uncalibrated heuristic: it can reject useful paraphrases and admit same-topic cases with different causes. Negation and long noisy descriptions are known weaknesses.

The local service has no live helpdesk connector, incremental index, persistent incoming-ticket store, agent UI, feedback capture, authentication, or per-agent authorization. The supplied history cannot validate real customer boundaries. Python's HTTP server is [not intended for production use](https://docs.python.org/3.12/library/http.server.html). A pilot needs identity-derived access checks, privacy controls, representative evaluation, monitored operation, and a production server.

## Repository guide

- `SOLUTION_DESIGN.md`: customer framing, assumptions, architecture, and tradeoffs.
- `ticket_assistant/`: import, retrieval engine, CLI, batch processing, and local API.
- `data/`: unchanged provider history/examples plus separately labeled evaluation queries.
- `provided/`: unchanged starter utility and README, retained for comparison.
- `tests/`: behavioral tests and separate adversarial fixtures.
- `evaluate.py`, `benchmark.py`, `VALIDATION.md`, `verification/`: reproducible checks and recorded evidence.
- `PANEL_WALKTHROUGH.md`: a suggested live demonstration and discussion points.
