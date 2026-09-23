"""Shared HTTP primitives for credentialed deployment verification.

The production smoke, persistence, and timeout checks deliberately remain small
standalone scripts.  Their transport rules are not independent, though: every
one handles credentials and must therefore share the same loopback-only origin,
bounded response, readiness, PDF, and multipart behaviour.
"""

from __future__ import annotations

import json
import os
import time
import tomllib
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
EXPECTED_READINESS = {
    "status": "ready",
    "datastore": "postgres",
    "schema": "complete",
}
MAX_ERROR_BODY_BYTES = 64 * 1024


def verification_base(variable: str, default: str) -> str:
    """Return a credential-safe, explicit loopback HTTP(S) origin."""
    value = os.getenv(variable, default).rstrip("/")
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{variable} has an invalid port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in LOOPBACK_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or port is None
    ):
        raise ValueError(f"{variable} must be an explicit loopback HTTP(S) origin")
    return value


@dataclass(frozen=True, slots=True)
class VerificationEndpoints:
    api: str
    web: str

    @classmethod
    def from_env(cls) -> VerificationEndpoints:
        return cls(
            api=verification_base("FINRISK_VERIFY_API", "http://127.0.0.1:8000"),
            web=verification_base("FINRISK_VERIFY_WEB", "http://127.0.0.1:3000"),
        )


def declared_runtime() -> str:
    project = Path(__file__).resolve().parents[2] / "pyproject.toml"
    version = tomllib.loads(project.read_text(encoding="utf-8"))["project"]["version"]
    return f"v{version}"


def request_json(
    url: str,
    payload: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    *,
    timeout: float = 30,
) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    request_headers = dict(headers or {})
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(
        url,
        data=data,
        headers=request_headers,
        method="POST" if data is not None else "GET",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def expect_http_status(
    request: Request,
    expected: int,
    *,
    timeout: float = 10,
) -> HTTPError:
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read(MAX_ERROR_BODY_BYTES)
    except HTTPError as exc:
        try:
            exc.read(MAX_ERROR_BODY_BYTES)
        finally:
            exc.close()
        if exc.code != expected:
            raise AssertionError(
                f"expected HTTP {expected}, received {exc.code}"
            ) from exc
        return exc
    raise AssertionError(f"expected HTTP {expected}, request succeeded")


def assert_readiness(payload: Mapping[str, Any]) -> None:
    """Reject a healthy-looking API backed by the wrong store or schema."""
    mismatches = {
        name: (expected, payload.get(name))
        for name, expected in EXPECTED_READINESS.items()
        if payload.get(name) != expected
    }
    if mismatches:
        raise RuntimeError(
            f"unexpected readiness payload (expected/actual): {mismatches!r}; "
            f"full payload: {payload!r}"
        )


def wait_for_json_object(
    url: str,
    *,
    timeout: float,
    label: str,
    interval: float = 2,
    request_timeout: float = 3,
    validator: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Poll a JSON endpoint until it returns a valid object contract."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            payload = request_json(url, timeout=request_timeout)
            if not isinstance(payload, dict):
                raise TypeError(f"unexpected {label} payload: {payload!r}")
            if validator is not None:
                validator(payload)
            return payload
        except (OSError, URLError, TypeError, ValueError, RuntimeError) as exc:
            last_error = exc
            time.sleep(interval)
    raise TimeoutError(f"{label} did not become ready: {last_error}")


def wait_for_readiness(
    api: str,
    *,
    timeout: float,
    interval: float = 2,
    request_timeout: float = 3,
) -> dict[str, Any]:
    return wait_for_json_object(
        f"{api}/health/ready",
        timeout=timeout,
        label="API",
        interval=interval,
        request_timeout=request_timeout,
        validator=assert_readiness,
    )


def pdf_with_text(text: str) -> bytes:
    """Return a small standards-compliant PDF without host dependencies."""
    lines = [line.replace("(", "\\(").replace(")", "\\)") for line in text.splitlines()]
    stream = (
        "BT /F1 11 Tf 72 720 Td "
        + " ".join(f"({line}) Tj T*" for line in lines)
        + " ET"
    ).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, item in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(item)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(
        b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    )
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def multipart(
    fields: Mapping[str, str],
    filename: str,
    content: bytes,
    *,
    boundary_prefix: str = "----finrisk",
) -> tuple[bytes, str]:
    boundary = f"{boundary_prefix}-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    parts.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/pdf\r\n\r\n",
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(parts), boundary
