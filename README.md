# Support Ticket Similarity Assistant

A runnable solution to the Solari Analytics FDE case study. It retrieves resolved historical tickets and their recorded fixes for a new incoming ticket, explains matching terms, and can return no suggestions.

The implementation uses the assessment's 40 historical tickets and four incoming examples unchanged. It runs locally with Python 3.11 or newer and has no third-party dependencies or API keys.

## Run the project

From the repository root:

```shell
cd support-ticket-assistant
python -m ticket_assistant demo
```

On Windows, `py -3` may be used instead of `python`; on macOS or Linux, `python3` may be needed.

```shell
python -m ticket_assistant batch --input data/new_tickets_example.json --json
python -m unittest discover -s tests -q
python -m ticket_assistant serve --port 8000
```

The service exposes a local JSON API, not a browser interface. See the [project README](support-ticket-assistant/README.md) for requests, schema details, and limitations.

## Review the submission

- [Solution design](support-ticket-assistant/SOLUTION_DESIGN.md): problem, assumptions, architecture, tradeoffs, and next steps.
- [Implementation and run instructions](support-ticket-assistant/README.md): CLI, batch flow, and API.
- [Validation](support-ticket-assistant/VALIDATION.md): 65 passing functional tests, relevance results, and measured limits.
- [Panel walkthrough](support-ticket-assistant/PANEL_WALKTHROUGH.md): demo sequence and discussion points.

The four supplied cases demonstrate two useful historical matches and two abstentions. The chart case includes a weaker secondary match. An additional hard negative exposes a false suggestion; the evaluator intentionally reports it with exit code 1. The artificial 55,000-record benchmark exceeds the proposed latency target. These results are documented rather than treated as production readiness.

## Guided presentation

From the repository root, run:

```shell
python present_to_panel.py
```

On Windows, double-click `START_PANEL_DEMO.cmd`. The helper uses an available Python installation and supports the bundled Codex runtime when present. Press Enter to advance through real searches, optional live tests, and clearly labeled recorded results. See [Present now](PRESENT_NOW.md).

Only synthetic assessment and regression data are included. Credentials, source screenshots, archives, and local preparation scripts are excluded.
