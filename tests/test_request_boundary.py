import asyncio

import pytest
from fastapi.testclient import TestClient
from finrisk.api import app
from finrisk.request_boundary import RequestBodyBoundary


def scope(headers=()):
    return {"type": "http", "method": "POST", "path": "/api/v1/assess", "headers": headers}


async def invoke(boundary, request_scope, chunks):
    sent, reads = [], []
    messages = iter(chunks)

    async def receive():
        reads.append(True)
        return next(messages)

    async def send(message):
        sent.append(message)

    await boundary(request_scope, receive, send)
    return sent, reads


@pytest.mark.parametrize("declared", [None, b"1"])
def test_json_measured_limit_precedes_parser(monkeypatch, declared):
    monkeypatch.setenv("FINRISK_MAX_REQUEST_BYTES", "8")

    async def parser(*_):
        pytest.fail("oversized JSON must not reach the parser")

    headers = [] if declared is None else [(b"content-length", declared)]
    sent, _ = asyncio.run(invoke(RequestBodyBoundary(parser), scope(headers), [
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"6789", "more_body": False},
    ]))
    assert sent[0]["status"] == 413


@pytest.mark.parametrize("length,status", [(b"9", 413), (b"-1", 400), (b"x", 400)])
def test_declared_json_limit_precedes_body_read(monkeypatch, length, status):
    monkeypatch.setenv("FINRISK_MAX_REQUEST_BYTES", "8")

    async def parser(*_):
        pytest.fail("invalid envelope must not reach the parser")

    sent, reads = asyncio.run(invoke(RequestBodyBoundary(parser), scope([(b"content-length", length)]), []))
    assert sent[0]["status"] == status and not reads


def test_direct_api_limits_unauthenticated_body_and_preserves_auth(monkeypatch):
    monkeypatch.setenv("FINRISK_MAX_REQUEST_BYTES", "128")
    client = TestClient(app)
    assert client.post("/api/v1/assess", content=b"x" * 129).status_code == 413
    assert client.post("/api/v1/assess", json={"company": "test", "fiscal_year": 2025, "current": {}}).status_code == 401
    monkeypatch.setenv("FINRISK_MAX_REQUEST_BYTES", "invalid")
    assert client.post("/api/v1/assess", content=b"{}").status_code == 503
    assert client.get("/health/live").status_code == 200


def test_slow_body_releases_capacity():
    async def scenario():
        async def parser(*_):
            pytest.fail("incomplete body must not reach the parser")

        async def receive():
            await asyncio.sleep(1)

        sent = []

        async def send(message):
            sent.append(message)

        boundary = RequestBodyBoundary(parser, read_timeout=0.01)
        await boundary(scope(), receive, send)
        assert sent[0]["status"] == 408
        assert not boundary.slots.locked()

    asyncio.run(scenario())
