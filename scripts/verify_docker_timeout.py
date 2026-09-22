"""Verify production proxy timeout and explicit retry contracts."""

from __future__ import annotations

import json
import os
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def verification_base(variable: str, default: str) -> str:
    value = os.getenv(variable, default).rstrip("/")
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{variable} has an invalid port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
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


API = verification_base("FINRISK_VERIFY_API", "http://127.0.0.1:8000")
WEB = verification_base("FINRISK_VERIFY_WEB", "http://127.0.0.1:3000")


def request_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def pdf_with_text(text: str) -> bytes:
    lines = [line.replace("(", "\\(").replace(")", "\\)") for line in text.splitlines()]
    stream = ("BT /F1 11 Tf 72 720 Td " + " ".join(f"({line}) Tj T*" for line in lines) + " ET").encode()
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
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def multipart(fields: dict[str, str], content: bytes) -> tuple[bytes, str]:
    boundary = f"----finrisk-timeout-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode(),
            b"\r\n",
        ])
    parts.extend([
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="file"; filename="timeout.pdf"\r\n',
        b"Content-Type: application/pdf\r\n\r\n",
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(parts), boundary


def main() -> None:
    """Verify the production proxy timeout and explicit retry contract.

    Importing this module must not make any request.
    """
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{API}/health/ready", timeout=3) as response:
                readiness = json.load(response)
                if (
                    readiness.get("status") == "ready"
                    and readiness.get("datastore") == "postgres"
                    and readiness.get("schema") == "complete"
                ):
                    break
        except (OSError, URLError, ValueError):
            time.sleep(1)
    else:
        raise SystemExit("timeout-smoke API readiness failed")

    # The web proxy is recreated by the same `docker compose up --force-recreate` as
    # the API, but every request below goes through it on :3000. Waiting only for the
    # API left a window in which Next.js had not bound its port yet, so the proxy
    # answered with a transport-level reset instead of an HTTP status. Waiting for the
    # proxy as well removes the race without weakening any assertion.
    proxy_deadline = time.monotonic() + 60
    while time.monotonic() < proxy_deadline:
        try:
            with urlopen(f"{WEB}/", timeout=3) as response:
                if response.status == 200:
                    break
        except (OSError, URLError, ValueError):
            time.sleep(1)
    else:
        raise SystemExit("timeout-smoke web proxy readiness failed")

    organization = request_json(
        f"{API}/api/v1/enterprise/organizations",
        {"name": "Timeout tenant", "actor_id": "timeout-admin"},
        {"X-Bootstrap-Token": os.environ["FINRISK_BOOTSTRAP_TOKEN"]},
    )
    headers = {"X-API-Key": organization["api_key"]}
    entity = request_json(
        f"{WEB}/api/v1/enterprise/entities",
        {"name": "Timeout issuer"},
        headers,
    )
    body, boundary = multipart(
        {"company": "Timeout issuer", "fiscal_year": "2025", "entity_id": entity["id"]},
        pdf_with_text("BALANCE SHEET\nCash and cash equivalents 100\nTotal assets 500"),
    )

    for attempt in (1, 2):
        correlation_id = f"timeout-retry-{attempt}"
        request = Request(
            f"{WEB}/api/v1/documents/analyze",
            data=body,
            headers={
                **headers,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "X-Correlation-Id": correlation_id,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                response.read(64 * 1024)
        except HTTPError as exc:
            payload = json.load(exc)
            response_correlation = exc.headers.get("X-Correlation-Id")
            exc.close()
            if exc.code != 504 or response_correlation != correlation_id:
                raise SystemExit(
                    f"timeout attempt {attempt} returned HTTP {exc.code}, correlation={response_correlation!r}"
                )
            if "timed out" not in str(payload.get("detail", "")).lower():
                raise SystemExit(f"timeout attempt {attempt} returned unsafe contract: {payload!r}")
        else:
            raise SystemExit(f"timeout attempt {attempt} unexpectedly succeeded")

    print("production proxy timeout and explicit retry contracts passed (504 x2)")


if __name__ == "__main__":
    main()
