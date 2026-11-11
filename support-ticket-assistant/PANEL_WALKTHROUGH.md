# Support Ticket Similarity Assistant walkthrough

## Opening explanation

The customer wants support agents to reuse relevant prior fixes and spend less time rediscovering solutions. This implementation takes an incoming ticket, retrieves resolved historical cases, and shows source text, recorded fixes, and matching terms. The agent decides whether a fix applies.

The default demo uses the assessment's 40 historical tickets and four incoming examples without modifying those files. The approach is a local BM25 baseline with no paid service or model dependency. It is a prototype; there is no claim of customer deployment, production security, or measured business improvement.

## Suggested live sequence

| Time | Demonstration | Point to explain |
| --- | --- | --- |
| 0-2 minutes | Restate the customer problem and assumptions | Similar symptoms justify investigation; they do not prove the same cause. |
| 2-6 minutes | Run `python -m ticket_assistant demo` | Explain the two useful matches and two abstentions across all supplied examples. |
| 6-9 minutes | Run batch JSON, then submit the native example to the API | The same engine supports offline review and a future helpdesk adapter. |
| 9-12 minutes | Open the importer and retrieval function; run tests/evaluation | Show source integrity, unknown metadata, validation, and retained quality failures. |
| 12-15 minutes | Discuss the pilot and scale assumptions | Separate measured local behavior from deployment targets. |
| Remaining time | Panel questions and a small change | Clarify the new requirement, reproduce the issue, and explain the tradeoff. |

## Explain the four examples

**NT-1 Password-reset email never arrives.** The engine abstains. T-1001 is about the password being rejected after the reset email arrived. Its copy-paste workaround does not fix email delivery. Do not present a superficially related case as a known resolution; ask for delivery diagnostics and retain this as new knowledge once solved.

**NT-2 Blank revenue chart.** T-1201 is ranked first and provides a useful empty-data comparison. Confirm the current query/filter result before reusing that explanation. T-1501 is also returned, but it concerns missing dashboard permissions and is a weaker, unlabeled candidate. This exposes a precision limitation.

**NT-3 Duplicate charge.** T-1303 is ranked first. It records a duplicate caused by payment retries. Verify the current charges and payment events; retrieving the ticket neither proves the same cause nor authorizes a refund.

**NT-4 Snowflake integration.** No strong match is returned. The history has other integrations, but their authentication fixes should not be presented as a Snowflake diagnosis. The behavior follows the general evidence gate; there is no Snowflake-specific rule.

## Questions to prepare for

**Why replace the starter helper?** It is a useful starting point but has no strict schema validation, eligibility filtering, or abstention gate. It ranks using raw token overlap and can return zero-overlap cases. The new engine adds explainable ranking and these boundaries. The original utility is preserved unchanged for comparison.

**Why no embeddings or generated summary?** Exact technical terms are a practical first baseline. A model adds hosting, privacy, latency, and evaluation work. Lexical search misses paraphrases, so I would compare hybrid search on independently labeled cases if that is a material failure mode. Retrieving the original resolution meets the request without generating another possible source of error.

**Does the score mean confidence?** No. It orders results within the query. The overlap gate is a separate uncalibrated heuristic. Even a high score can indicate shared wording with a different root cause. The recorded validation includes false suggestions.

**Why not use tags and resolution notes in matching?** They may have been added after the issue was solved. The seed does not say when they became available. The initial version searches symptoms and preserves tags and resolutions as reference metadata; a later experiment can test whether using reliably available fields improves quality.

**Can you demonstrate customer isolation?** The provider data contains no customer IDs, so it cannot establish customer-specific permissions. It is imported under a dataset namespace. Separate fixtures verify the engine's tenant-filtering invariant, but production must derive allowed scopes from authenticated identity and enforce agent access. Cross-customer reuse needs an approved sanitized knowledge layer.

**What about old or reopened tickets?** Created dates are displayed honestly; resolution dates remain unknown. The demo indexes a snapshot and requires restart after changes. A helpdesk adapter would process versioned, idempotent updates, reopen/delete events, and resolution corrections. An assistant outage must not block ticket intake.

**How does tenfold growth change the design?** Separate arrival rate, history size, and peak concurrency. About 55,000 arrivals a year is a planning assumption at 150 per day. The artificial benchmark repeats seed records and is not a capacity guarantee. Measure representative history and bursts, then adopt a persistent index and asynchronous updates when warranted.

**What would prove business value?** Agree with the support lead on relevant versus harmful suggestions, collect independent labels using only history available at each query time, then run a small pilot. Measure useful suggestions, coverage, false suggestions, lookup time, and agent adoption against a baseline. Do not equate synthetic retrieval results with business improvement.

## Practice a bounded change

Run:

```shell
python -m ticket_assistant search --title "Charged twice this month" --description "Two charges for one monthly subscription." --category billing
python -m ticket_assistant search --title "Charged twice this month" --description "Two charges for one monthly subscription." --category billing --exclude-ticket-id T-1303
```

Explain category filtering and self-exclusion, then inspect how the result changes. If asked to improve recall, first reproduce a missed query and check the effect on hard negatives. Reducing the threshold without measuring wrong suggestions is not sufficient.
