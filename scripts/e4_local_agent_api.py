"""Minimal OpenAI-compatible HTTP boundary for the isolated E4 local model.

The service has one fixed backend and no tool, shell, repository, or arbitrary
host-filesystem integration.  It is intended to run on an internal Docker
network with this single file mounted read-only.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

BACKEND = os.environ.get("E4_OLLAMA_URL", "http://finrisk-e4-ollama:11434").rstrip("/")
MODEL = os.environ.get("E4_MODEL", "qwen2.5:0.5b")
MAX_BODY = 2 * 1024 * 1024


def _backend_url(path: str) -> str:
    parsed = urllib.parse.urlparse(BACKEND)
    if parsed.scheme != "http" or parsed.hostname != "finrisk-e4-ollama":
        raise RuntimeError("E4 backend must be the isolated finrisk-e4-ollama service")
    return f"{BACKEND}{path}"


def _request(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(
        _backend_url(path),
        data=body,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read())


class Handler(BaseHTTPRequestHandler):
    server_version = "FinRiskE4LocalAgent/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, value: dict[str, Any]) -> None:
        payload = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        try:
            if self.path == "/health":
                tags = _request("/api/tags")
                available = any(row.get("name") == MODEL for row in tags.get("models", []))
                self._send(200 if available else 503, {"status": "ok" if available else "unavailable", "model": MODEL})
                return
            if self.path == "/v1/models":
                tags = _request("/api/tags")
                models = [row for row in tags.get("models", []) if row.get("name") == MODEL]
                self._send(200, {"object": "list", "data": [{"id": row["name"], "object": "model", "owned_by": "local"} for row in models]})
                return
            self._send(404, {"error": "not_found"})
        except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
            self._send(503, {"error": type(exc).__name__})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                self._send(413, {"error": "invalid_body_size"})
                return
            incoming = json.loads(self.rfile.read(length))
            if incoming.get("model") != MODEL or incoming.get("stream") not in {None, False}:
                self._send(400, {"error": "unsupported_model_or_stream"})
                return
            messages = incoming.get("messages")
            if not isinstance(messages, list) or not messages:
                self._send(400, {"error": "messages_required"})
                return
            response_format = incoming.get("response_format", {})
            schema = response_format.get("json_schema", {}).get("schema")
            if not isinstance(schema, dict):
                self._send(400, {"error": "json_schema_required"})
                return
            options = incoming.get("options", {})
            allowed_options = {key: options[key] for key in ("temperature", "seed", "num_ctx", "num_predict", "num_thread") if key in options}
            started = time.monotonic()
            result = _request(
                "/api/chat",
                {"model": MODEL, "messages": messages, "stream": False, "format": schema, "options": allowed_options},
            )
            content = result.get("message", {}).get("content", "")
            json.loads(content)
            self._send(
                200,
                {
                    "id": f"e4-local-{time.time_ns()}",
                    "object": "chat.completion",
                    "model": MODEL,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": result.get("done_reason", "stop")}],
                    "usage": {
                        "prompt_tokens": result.get("prompt_eval_count"),
                        "completion_tokens": result.get("eval_count"),
                        "total_duration_ns": result.get("total_duration"),
                        "boundary_latency_ms": round((time.monotonic() - started) * 1000, 3),
                    },
                },
            )
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError, urllib.error.URLError) as exc:
            self._send(502, {"error": type(exc).__name__})


def main() -> None:
    host = os.environ.get("E4_AGENT_HOST", "0.0.0.0")
    port = int(os.environ.get("E4_AGENT_PORT", "8080"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
