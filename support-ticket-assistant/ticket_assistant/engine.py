"""Deterministic lexical retrieval with a deliberately conservative match gate.

Only a fixed scope's resolved tickets with recorded resolutions are indexed.
The supplied assessment history has no tenant identity; its fixed namespace is
a dataset scope, not proof of customer isolation or authorization.
BM25 searches the title (twice) and description; resolution text is returned as
evidence, never used for ranking. Scores are relative ranking values, not
probabilities or confidence estimates.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
import json
import math
from pathlib import Path
import re
from typing import Any


REQUIRED_FIELDS = (
    "id", "tenant_id", "title", "description", "product", "status",
    "resolution", "resolved_at",
)
SEED_NAMESPACE = "solari-seed"
SEED_FIELDS = (
    "ticket_id", "subject", "description", "resolution_notes", "category",
    "tags", "created_at", "status",
)
MAX_QUERY_CHARS = 10_000
MAX_LIMIT = 10
MIN_QUERY_COVERAGE = 0.25
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[_./:-][a-z0-9]+)*", re.ASCII)
ERROR_CODE_PATTERN = re.compile(
    r"(?=[a-z0-9_-]*[a-z])(?=[a-z0-9_-]*[0-9])[a-z0-9]+(?:[_-][a-z0-9]+)+\Z"
)
# Remove conversational boilerplate, not technical terms such as timeout,
# login, certificate or export. No learned or hidden synonym expansion.
STOP_WORDS = frozenset("""
    a after all an and are as at be been before being but by can cannot could did do does doing
    for from had has have having he her here him his how i if in into is it its
    me my not of on only or our out please she should so some than that the their
    them then there these they this those through to too us was we were what
    when where which while who why will with would you your
    ticket tickets issue issues problem problems help thanks thank need needs
    using use used getting get gets customer customers team user users
""".split())


def tokenize(text: str) -> list[str]:
    """Lowercase words, preserving technical identifiers such as ERR_AUTH_401."""
    return [
        token for token in TOKEN_PATTERN.findall(text.lower())
        if token not in STOP_WORDS and len(token) > 1
    ]


def _validate_date(value: Any, field: str, prefix: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        suffix = " or null" if nullable else ""
        raise ValueError(f"{prefix} {field} must be YYYY-MM-DD{suffix}.")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{prefix} {field} is not a valid date.") from exc


def _validate_utf8(value: str, field: str, prefix: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{prefix} field {field} must contain valid Unicode text.") from exc


def _validate_tags(value: Any, prefix: str) -> None:
    if not isinstance(value, list) or any(not isinstance(tag, str) or not tag.strip() for tag in value):
        raise ValueError(f"{prefix} tags must be an array of nonblank strings.")
    for tag in value:
        _validate_utf8(tag, "tags", prefix)


def _adapt_seed_records(records: Any) -> list[dict[str, Any]]:
    """Map the supplied schema without inventing tenant or resolution dates."""
    if not isinstance(records, list):
        raise ValueError("The tickets field must be an array of ticket objects.")
    normalized = []
    for position, record in enumerate(records, start=1):
        prefix = f"Seed ticket at position {position}"
        if not isinstance(record, dict):
            raise ValueError(f"{prefix} must be an object.")
        missing = [field for field in SEED_FIELDS if field not in record]
        if missing:
            raise ValueError(f"{prefix} is missing: {', '.join(missing)}.")
        if "tenant_id" in record:
            raise ValueError(f"{prefix} contains tenant_id; use the canonical array schema to preserve tenant identity.")
        for field in SEED_FIELDS:
            if field != "tags" and not isinstance(record[field], str):
                raise ValueError(f"{prefix} field {field} must be a string.")
            if field != "tags":
                _validate_utf8(record[field], field, prefix)
        for field in ("ticket_id", "subject", "category", "status"):
            if not record[field].strip():
                raise ValueError(f"{prefix} field {field} must not be blank.")
        _validate_tags(record["tags"], prefix)
        _validate_date(record["created_at"], "created_at", prefix)
        normalized.append({
            "id": record["ticket_id"],
            "tenant_id": SEED_NAMESPACE,
            "title": record["subject"],
            "description": record["description"],
            # The existing engine's exact filter is named product. For this
            # schema it carries a category, never an invented product name.
            "product": record["category"],
            "status": record["status"],
            "resolution": record["resolution_notes"],
            "resolved_at": None,
            "category": record["category"],
            "created_at": record["created_at"],
            "tags": list(record["tags"]),
            "source_schema": "assessment_seed",
            "scope_kind": "dataset",
        })
    return normalized


def _validate_tickets(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError("Ticket data must be a JSON array of ticket objects.")
    validated: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for position, record in enumerate(records, start=1):
        prefix = f"Ticket at position {position}"
        if not isinstance(record, dict):
            raise ValueError(f"{prefix} must be an object.")
        missing = [field for field in REQUIRED_FIELDS if field not in record]
        if missing:
            raise ValueError(f"{prefix} is missing: {', '.join(missing)}.")
        for field in REQUIRED_FIELDS[:-1]:
            if not isinstance(record[field], str):
                raise ValueError(f"{prefix} field {field} must be a string.")
            _validate_utf8(record[field], field, prefix)
        for field in ("id", "tenant_id", "title", "product", "status"):
            if not record[field].strip():
                raise ValueError(f"{prefix} field {field} must not be blank.")
        timestamp = record["resolved_at"]
        _validate_date(timestamp, "resolved_at", prefix, nullable=True)
        seed_record = record.get("source_schema") == "assessment_seed"
        if seed_record:
            if record["tenant_id"] != SEED_NAMESPACE or record.get("scope_kind") != "dataset":
                raise ValueError(f"{prefix} assessment seed must use its dataset namespace.")
            if record.get("category") != record["product"]:
                raise ValueError(f"{prefix} assessment category must match the internal filter value.")
            _validate_date(record.get("created_at"), "created_at", prefix)
            _validate_tags(record.get("tags"), prefix)
            if timestamp is not None:
                raise ValueError(f"{prefix} assessment seed does not supply a resolution date.")
        elif record["status"] == "resolved" and timestamp is None:
            raise ValueError(f"{prefix} requires resolved_at when status is resolved.")
        identity = (record["tenant_id"], record["id"])
        if identity in identities:
            raise ValueError(f"{prefix} duplicates an id within its tenant.")
        identities.add(identity)
        # Return only the documented schema, avoiding accidental disclosure of
        # unrelated source fields. Copy records so callers cannot mutate index
        # state through their original input dictionaries.
        clean = {field: record[field] for field in REQUIRED_FIELDS}
        if seed_record:
            for field in ("category", "created_at", "tags", "source_schema", "scope_kind"):
                clean[field] = deepcopy(record[field])
        validated.append(clean)
    return validated


def load_tickets(path: str | Path) -> list[dict[str, Any]]:
    """Load a supplied {tickets: [...]} wrapper or a legacy canonical array.

    Supplied creation dates and tags remain source metadata. Neither creation
    date nor category is presented as a resolution date or a product identity.
    """
    try:
        with Path(path).open(encoding="utf-8-sig") as handle:
            records = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load ticket data: {exc}") from exc
    if isinstance(records, dict):
        if "tickets" not in records:
            raise ValueError("Ticket data object must contain a tickets array.")
        records = _adapt_seed_records(records["tickets"])
    return _validate_tickets(records)


class SearchEngine:
    """An immutable, fixed-scope in-memory index for a small history.

    Construction validates the complete input. Only eligible records contribute
    to document frequency and average document length, so another scope does
    not affect either results or scores. The assessment scope is a dataset
    namespace because its source records contain no customer identities.
    Rebuild the index to refresh history.
    """

    def __init__(self, tickets: list[dict[str, Any]], tenant_id: str):
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a nonblank string.")
        records = _validate_tickets(tickets)
        self.tenant_id = tenant_id
        self._tickets = [
            record for record in records
            if record["tenant_id"] == tenant_id
            and record["status"] == "resolved"
            and record["resolution"].strip()
        ]
        self._term_frequencies = [
            Counter(tokenize(f"{record['title']} {record['title']} {record['description']}"))
            for record in self._tickets
        ]
        self._lengths = [sum(counts.values()) for counts in self._term_frequencies]
        self._average_length = sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        self._document_frequency: Counter[str] = Counter()
        self._postings: dict[str, set[int]] = defaultdict(set)
        self._product_indices: dict[str, set[int]] = defaultdict(set)
        self._id_indices: dict[str, int] = {}
        for index, counts in enumerate(self._term_frequencies):
            self._document_frequency.update(counts.keys())
            for term in counts:
                self._postings[term].add(index)
            self._product_indices[self._tickets[index]["product"]].add(index)
            self._id_indices[self._tickets[index]["id"]] = index

    def search(
        self,
        title: str,
        description: str = "",
        limit: int = 3,
        exclude_ticket_id: str | None = None,
        product: str | None = None,
    ) -> dict[str, Any]:
        """Return source resolutions for likely lexical matches, or abstain.

        A candidate passes with at least two distinct matching query terms and
        25% query coverage, or one exact distinctive alphanumeric code containing
        an underscore/hyphen (for example ERR_AUTH_401). A generic single word
        never produces a suggestion. This heuristic is explicit and should be
        calibrated against real agent relevance labels before deployment.
        """
        if not isinstance(title, str) or not isinstance(description, str):
            raise ValueError("title and description must be strings.")
        if len(title) + len(description) > MAX_QUERY_CHARS:
            raise ValueError(f"title and description together must not exceed {MAX_QUERY_CHARS} characters.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be an integer between 1 and {MAX_LIMIT}.")
        for name, value in (("exclude_ticket_id", exclude_ticket_id), ("product", product)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a nonblank string or null.")
        query_terms = sorted(set(tokenize(f"{title} {description}")))
        query_codes = {term for term in query_terms if ERROR_CODE_PATTERN.fullmatch(term)}
        eligible_indices = (
            set(range(len(self._tickets))) if product is None
            else set(self._product_indices.get(product, ()))
        )
        if exclude_ticket_id in self._id_indices:
            eligible_indices.discard(self._id_indices[exclude_ticket_id])
        response: dict[str, Any] = {
            "query_terms": query_terms,
            "results": [],
            "reason": "no_match",
            "total_eligible": len(eligible_indices),
        }
        if len(query_terms) < 2 and not query_codes:
            response["reason"] = "insufficient_query"
            return response

        k1, b = 1.5, 0.75
        corpus_size = len(self._tickets)
        matches: list[tuple[float, dict[str, Any]]] = []
        candidate_indices: set[int] = set()
        for term in query_terms:
            candidate_indices.update(self._postings.get(term, ()))
        for index in candidate_indices & eligible_indices:
            frequencies = self._term_frequencies[index]
            overlap = [term for term in query_terms if term in frequencies]
            exact_code_match = any(term in query_codes for term in overlap)
            passes_overlap_gate = (
                len(overlap) >= 2 and len(overlap) / len(query_terms) >= MIN_QUERY_COVERAGE
            )
            if not (exact_code_match or passes_overlap_gate):
                continue
            length_ratio = self._lengths[index] / self._average_length if self._average_length else 0.0
            score = 0.0
            for term in overlap:
                frequency = frequencies[term]
                doc_frequency = self._document_frequency[term]
                inverse_frequency = math.log(1 + (corpus_size - doc_frequency + 0.5) / (doc_frequency + 0.5))
                score += inverse_frequency * frequency * (k1 + 1) / (
                    frequency + k1 * (1 - b + b * length_ratio)
                )
            record = self._tickets[index]
            warnings = ["Verify that the recorded resolution applies to the current product version and context."]
            if record.get("source_schema") == "assessment_seed":
                warnings.append("The source provides a ticket creation date, not a resolution date.")
            if not passes_overlap_gate:
                warnings.append("Matched an exact error identifier; check the surrounding symptoms before reusing the resolution.")
            matches.append((score, {
                "ticket": deepcopy(record),
                "score": round(score, 4),
                "matched_terms": overlap,
                "warnings": warnings,
            }))
        # Sort on unrounded scores; IDs provide a stable tie-break independent
        # of input order. Recency remains visible evidence, not a relevance boost.
        matches.sort(key=lambda item: (-item[0], item[1]["ticket"]["id"]))
        response["results"] = [match for _, match in matches[:limit]]
        if response["results"]:
            response["reason"] = "matches"
        return response
