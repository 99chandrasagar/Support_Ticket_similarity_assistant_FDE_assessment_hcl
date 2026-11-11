"""Command-line entry point for the Support Ticket Similarity Assistant."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import SearchEngine, load_tickets
from .server import make_server, validate_request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "tickets.json"
DEFAULT_EXAMPLES = ROOT / "data" / "new_tickets_example.json"


def _show_result(result: dict) -> None:
    if not result["results"]:
        if result["reason"] == "insufficient_query":
            print("No suggestion: add an error code or more specific issue details.")
        else:
            print("No suggestion: no past ticket met the minimum evidence rule.")
        return
    for number, match in enumerate(result["results"], start=1):
        ticket = match["ticket"]
        print(f"\n{number}. {ticket['id']} | {ticket['title']}")
        created = ticket.get("created_at") or "not supplied"
        resolved = ticket.get("resolved_at") or "not supplied"
        print(f"   Category: {ticket['product']} | Created: {created} | Resolved date: {resolved}")
        print(f"   Ranking score: {match['score']:.3f} (not a confidence percentage)")
        print(f"   Matched terms: {', '.join(match['matched_terms'])}")
        print(f"   Historical issue: {ticket['description']}")
        print(f"   Stored resolution: {ticket['resolution']}")
        for warning in match.get("warnings", []):
            print(f"   Note: {warning}")
    print("\nCheck the source ticket and current product behavior before reusing a resolution.")


def load_incoming(path: Path, limit: int = 3) -> list[dict]:
    """Validate the provider's new_tickets envelope without changing the file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load incoming tickets: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {"new_tickets"}:
        raise ValueError("Incoming file must contain one new_tickets array.")
    incoming = payload["new_tickets"]
    if not isinstance(incoming, list) or not incoming:
        raise ValueError("new_tickets must be a non-empty array.")
    seen: set[str] = set()
    normalized = []
    for position, ticket in enumerate(incoming, start=1):
        if not isinstance(ticket, dict) or "ticket_id" not in ticket or "subject" not in ticket:
            raise ValueError(f"Incoming ticket {position} requires ticket_id and subject.")
        arguments = validate_request({**ticket, "limit": limit})
        identifier = ticket["ticket_id"]
        if identifier in seen:
            raise ValueError("Incoming ticket_id values must be unique.")
        seen.add(identifier)
        normalized.append({"ticket_id": identifier, "subject": ticket["subject"], "arguments": arguments})
    return normalized


def run_batch(engine: SearchEngine, incoming: list[dict]) -> dict:
    return {
        "new_tickets": [
            {"ticket_id": ticket["ticket_id"], "subject": ticket["subject"], "suggestions": engine.search(**ticket["arguments"])}
            for ticket in incoming
        ]
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find resolved historical support tickets. Local demo; no external services.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    commands = {}
    for name, help_text in (
        ("demo", "Run all four incoming tickets supplied with the assessment"),
        ("batch", "Suggest past resolutions for a new_tickets JSON file"),
        ("search", "Suggest past resolutions for one incoming ticket"),
        ("serve", "Start the loopback-only JSON API"),
    ):
        subparser = subparsers.add_parser(name, help=help_text)
        subparser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Path to history JSON (default: supplied data/tickets.json)")
        subparser.add_argument("--tenant", default="solari-seed", help="Fixed dataset namespace (default: solari-seed)")
        commands[name] = subparser
    commands["search"].add_argument("--title", required=True)
    commands["search"].add_argument("--description", default="")
    commands["search"].add_argument("--category", "--product", dest="product", help="Exact history category, such as auth or billing")
    commands["search"].add_argument("--exclude-ticket-id")
    commands["search"].add_argument("--limit", type=int, default=3)
    commands["search"].add_argument("--json", action="store_true", help="Print the complete structured result")
    commands["batch"].add_argument("--input", type=Path, required=True, help="JSON file with the provider's new_tickets array")
    commands["batch"].add_argument("--limit", type=int, default=3)
    commands["batch"].add_argument("--json", action="store_true")
    commands["serve"].add_argument("--port", type=int, default=8000, help="Local TCP port (default: 8000)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        engine = SearchEngine(load_tickets(args.data), tenant_id=args.tenant)
        if args.command == "search":
            arguments = validate_request({
                "title": args.title,
                "description": args.description,
                "product": args.product,
                "exclude_ticket_id": args.exclude_ticket_id,
                "limit": args.limit,
            })
            result = engine.search(**arguments)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
            else:
                _show_result(result)
            return 0
        if args.command in ("demo", "batch"):
            incoming = load_incoming(DEFAULT_EXAMPLES if args.command == "demo" else args.input, limit=3 if args.command == "demo" else args.limit)
            result = run_batch(engine, incoming)
            if args.command == "batch" and args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
                return 0
            print("Support Ticket Similarity Assistant")
            print("Read-only local demonstration. Default files are the assessment's supplied synthetic history and incoming examples.")
            print("Ticket creation dates are source metadata; resolution dates are not supplied.")
            for ticket in result["new_tickets"]:
                print(f"\nIncoming {ticket['ticket_id']}: {ticket['subject']}")
                _show_result(ticket["suggestions"])
            return 0
        if not 1 <= args.port <= 65535:
            raise ValueError("port must be between 1 and 65535.")
        server = make_server(engine, port=args.port)
        print(f"Listening on http://127.0.0.1:{server.server_address[1]}", flush=True)
        print("Local demo only. Search scope is fixed at startup; the supplied seed has no customer identity.", flush=True)
        print("No production authentication or helpdesk integration.", flush=True)
        print("GET /health | POST /suggest | Ctrl+C to stop", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping server.")
        finally:
            server.server_close()
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
