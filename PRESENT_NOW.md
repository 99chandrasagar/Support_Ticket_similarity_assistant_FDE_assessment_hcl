# Present the support ticket assistant

Open PowerShell in the repository root and run:

```powershell
.\START_PANEL_DEMO.cmd
```

The guide pauses before each step. Share the terminal window and use Enter to advance. The four ticket screens execute real retrieval against the supplied seed files. The test screen can run the functional suite live. Recorded evaluation and performance figures are labeled as recorded.

## Opening words

"Solari's support agents need to reuse previous fixes quickly and consistently. My proposed first version retrieves relevant resolved tickets, shows their recorded fixes and why they matched, and lets the agent verify whether the fix applies. I used the supplied 40-ticket dataset and built a local retrieval engine, batch flow, and API. I will show useful matches, cases where it returns no suggestion, and the limitations I found."

## A ten minute sequence

| Time | What to show |
| --- | --- |
| 1 minute | State the problem and scope on the launcher's opening screen. |
| 4 minutes | Walk through duplicate billing, blank chart, Snowflake, and missing reset email. |
| 2 minutes | Run tests and explain recorded relevance results, including incorrect suggestions. |
| 2 minutes | Open SOLUTION_DESIGN.md and explain the architecture and why BM25 was chosen. |
| 1 minute | Explain production gaps, the missed latency target, and next steps. |

Keep SOLUTION_DESIGN.md and ticket_assistant/engine.py open for questions. Use PANEL_WALKTHROUGH.md privately for preparation. Share the terminal or project window; keep the credential PDF closed.

## Statements to make accurately

- A ranking score is not a confidence percentage.
- The chart's second suggestion is weaker and not labeled relevant.
- No suggestion is useful when the history lacks a relevant resolution.
- The supplied data has no customer IDs or resolution timestamps.
- Functional tests pass, while a retained relevance test fails.
- The artificial 55,000-record p95 exceeds the proposed 500 ms target; production scale is not established.
- AI enhancements are optional in the assessment. The current app uses no external AI model.

If asked about a detail you have not verified, explain what you would inspect or measure. Describe development assistance accurately if the panel asks.
