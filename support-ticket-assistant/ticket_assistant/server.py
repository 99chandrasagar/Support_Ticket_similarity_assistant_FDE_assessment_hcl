"""Read-only, loopback-only demonstration API; not a production HTTP server."""

from __future__ import annotations

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .engine import MAX_QUERY_CHARS

MAX_BODY_BYTES = 32_768
MAX_TITLE_CHARS = 300
MAX_DESCRIPTION_CHARS = 10_000


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON fields are not allowed.")
        result[key] = value
    return result


def validate_request(payload: Any) -> dict[str, Any]:
    """Normalize one native or canonical query; identity is never request input."""
    if not isinstance(payload, dict):
        raise ValueError("The JSON body must be an object.")
    for value in payload.values():
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("Text fields must contain valid Unicode characters.") from exc
    native = "subject" in payload or "ticket_id" in payload
    if native:
        if any(field in payload for field in ("title", "product", "exclude_ticket_id")):
            raise ValueError("Do not mix native subject/ticket_id fields with canonical title/product/exclude_ticket_id fields.")
        allowed = {"subject", "ticket_id", "description", "category", "limit"}
    else:
        allowed = {"title", "description", "product", "category", "exclude_ticket_id", "limit"}
    if set(payload) - allowed:
        raise ValueError("Unsupported fields. Search scope is set when the server starts.")
    if "category" in payload and "product" in payload:
        raise ValueError("Provide category or product, not both.")
    title = payload.get("subject" if native else "title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("subject/title must be a non-empty string.")
    if len(title) > MAX_TITLE_CHARS:
        raise ValueError(f"title must contain at most {MAX_TITLE_CHARS} characters.")
    description = payload.get("description", "")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION_CHARS:
        raise ValueError(f"description must be a string of at most {MAX_DESCRIPTION_CHARS} characters.")
    if len(title) + len(description) > MAX_QUERY_CHARS:
        raise ValueError(f"title and description together must not exceed {MAX_QUERY_CHARS} characters.")
    limit = payload.get("limit", 3)
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("limit must be an integer from 1 to 10.")
    result: dict[str, Any] = {"title": title, "description": description, "limit": limit}
    fields = {
        "product": "category" if "category" in payload else "product",
        "exclude_ticket_id": "ticket_id" if native else "exclude_ticket_id",
    }
    if native and "ticket_id" not in payload:
        raise ValueError("Native requests require ticket_id and subject.")
    for name, source_name in fields.items():
        value = payload.get(source_name)
        if native and source_name == "ticket_id" and value is None:
            raise ValueError("ticket_id must be a non-empty string of at most 100 characters.")
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > 100:
                raise ValueError(f"{source_name} must be a non-empty string of at most 100 characters.")
            result[name] = value
    return result


def make_server(engine: Any, port: int = 8000) -> ThreadingHTTPServer:
    """Create a server bound to 127.0.0.1, with an immutable tenant-scoped engine."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "TicketAssistantDemo/1.0"
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format: str, *args: Any) -> None:
            # The default logger includes attacker-controlled URLs and query text.
            # This local demo intentionally does not log request content.
            return

        def _send_json(self, status: int, data: dict[str, Any]) -> None:
            body = json.dumps(data, ensure_ascii=True, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def _local_request(self) -> bool:
            port_number = self.server.server_address[1]
            allowed_hosts = {f"127.0.0.1:{port_number}", f"localhost:{port_number}"}
            if port_number == 80:
                allowed_hosts.update({"127.0.0.1", "localhost"})
            host_headers = self.headers.get_all("Host", [])
            if len(host_headers) != 1 or host_headers[0].lower() not in allowed_hosts:
                self._send_json(403, {"error": "Only local requests are allowed."})
                return False
            origins = self.headers.get_all("Origin", [])
            if origins and (len(origins) != 1 or origins[0].lower() not in {
                f"http://{host}" for host in allowed_hosts
            }):
                self._send_json(403, {"error": "Cross-origin requests are not allowed."})
                return False
            return True

        def do_GET(self) -> None:
            if not self._local_request():
                return
            if self.path != "/health":
                self._send_json(404, {"error": "Route not found. Use GET /health or POST /suggest."})
                return
            self._send_json(200, {"status": "ok", "mode": "local-demo"})

        def do_POST(self) -> None:
            if not self._local_request():
                return
            if self.path != "/suggest":
                self._send_json(404, {"error": "Route not found. Use POST /suggest."})
                return
            if self.headers.get_all("Transfer-Encoding"):
                self._send_json(400, {"error": "Transfer-Encoding is not supported."})
                return
            lengths = self.headers.get_all("Content-Length", [])
            if not lengths:
                self._send_json(411, {"error": "Content-Length is required."})
                return
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
                self._send_json(400, {"error": "A single non-negative Content-Length is required."})
                return
            if len(lengths[0]) > 10:
                self._send_json(413, {"error": f"Request body exceeds {MAX_BODY_BYTES} bytes."})
                return
            length = int(lengths[0])
            if length > MAX_BODY_BYTES:
                self._send_json(413, {"error": f"Request body exceeds {MAX_BODY_BYTES} bytes."})
                return
            content_types = self.headers.get_all("Content-Type", [])
            if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
                self._send_json(415, {"error": "Content-Type must be application/json."})
                return
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete request body.")
                payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
                arguments = validate_request(payload)
                result = engine.search(**arguments)
                if "ticket_id" in payload:
                    result["incoming_ticket_id"] = payload["ticket_id"]
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, (UnicodeDecodeError, json.JSONDecodeError)) else "Body must be valid UTF-8 JSON."
                self._send_json(400, {"error": message})
                return
            except (TimeoutError, socket.timeout):
                self._send_json(408, {"error": "Timed out reading request body."})
                return
            except Exception:
                self._send_json(500, {"error": "Suggestion service failed. Check the local dataset and restart."})
                return
            self._send_json(200, result)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
