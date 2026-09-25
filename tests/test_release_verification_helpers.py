from __future__ import annotations

import io
import json
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from finrisk import verification_http as http


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_release_origins_are_loopback_only(monkeypatch):
    monkeypatch.setenv("FINRISK_VERIFY_API", "http://localhost:8123/")
    monkeypatch.setenv("FINRISK_VERIFY_WEB", "https://[::1]:3443")
    endpoints = http.VerificationEndpoints.from_env()
    assert endpoints.api == "http://localhost:8123"
    assert endpoints.web == "https://[::1]:3443"
    assert http.declared_runtime() == "v0.3.4"

    invalid = [
        "https://example.com:443",
        "http://user:secret@localhost:8000",
        "http://127.0.0.1:8000/path",
        "http://127.0.0.1:not-a-port",
    ]
    for value in invalid:
        monkeypatch.setenv("VERIFY_ORIGIN", value)
        with pytest.raises(ValueError, match="VERIFY_ORIGIN"):
            http.verification_base("VERIFY_ORIGIN", "http://127.0.0.1:1")


def test_json_transport_and_expected_error_contract(monkeypatch):
    captured = {}

    def open_json(request, timeout):
        captured.update(
            method=request.method,
            content_type=request.headers["Content-type"],
            body=json.loads(request.data),
            timeout=timeout,
        )
        return _Response(b'{"ok": true}')

    monkeypatch.setattr(http, "urlopen", open_json)
    assert http.request_json("http://127.0.0.1:1/x", {"x": 1}, timeout=4) == {
        "ok": True
    }
    assert captured == {
        "method": "POST",
        "content_type": "application/json",
        "body": {"x": 1},
        "timeout": 4,
    }

    def open_error(_request, timeout):
        assert timeout == 10
        raise HTTPError("http://127.0.0.1", 401, "denied", {}, io.BytesIO(b"x"))

    monkeypatch.setattr(http, "urlopen", open_error)
    error = http.expect_http_status(Request("http://127.0.0.1"), 401)
    assert error.code == 401

    with pytest.raises(AssertionError, match="received 401"):
        http.expect_http_status(Request("http://127.0.0.1"), 403)

    monkeypatch.setattr(http, "urlopen", lambda *_args, **_kwargs: _Response(b"ok"))
    with pytest.raises(AssertionError, match="request succeeded"):
        http.expect_http_status(Request("http://127.0.0.1"), 401)


def test_readiness_polling_retries_and_validates(monkeypatch):
    http.assert_readiness(dict(http.EXPECTED_READINESS))
    with pytest.raises(RuntimeError, match="unexpected readiness"):
        http.assert_readiness({"status": "ready", "datastore": "memory"})

    responses = iter([OSError("starting"), ["wrong"], dict(http.EXPECTED_READINESS)])

    def request(_url, **_kwargs):
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(http, "request_json", request)
    monkeypatch.setattr(http.time, "sleep", lambda _seconds: None)
    result = http.wait_for_readiness(
        "http://127.0.0.1:8000", timeout=2, interval=0, request_timeout=1
    )
    assert result == http.EXPECTED_READINESS

    ticks = iter([0.0, 0.5, 1.1])
    monkeypatch.setattr(http.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(http, "request_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("down")))
    with pytest.raises(TimeoutError, match="did not become ready"):
        http.wait_for_json_object("http://127.0.0.1", timeout=1, label="service", interval=0)


def test_pdf_and_multipart_payloads_are_well_formed(monkeypatch):
    pdf = http.pdf_with_text("Risk (high)\nsecond line")
    assert pdf.startswith(b"%PDF-1.4")
    assert b"startxref" in pdf

    monkeypatch.setattr(http.uuid, "uuid4", lambda: type("U", (), {"hex": "fixed"})())
    body, boundary = http.multipart(
        {"company": "E4_COMPANY_000001"}, "packet.pdf", pdf
    )
    assert boundary == "----finrisk-fixed"
    assert b'E4_COMPANY_000001' in body
    assert b'filename="packet.pdf"' in body
    assert body.endswith(b"------finrisk-fixed--\r\n")
