import asyncio
import tracemalloc

import pytest
from fastapi.testclient import TestClient
from finrisk import api
from finrisk import upload_boundary as module
from finrisk.enterprise.security import RateLimiterUnavailable
from finrisk.upload_boundary import MULTIPART_OVERHEAD_BYTES, UploadBoundary
from starlette.exceptions import HTTPException


def scope(headers=(), path="/api/v1/documents/analyze"):
    return {"type": "http", "method": "POST", "path": path, "headers": list(headers)}


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


def reject_auth(key):
    raise HTTPException(401, "invalid API key")


def test_unauthenticated_request_never_reads_or_parses_body():
    async def parser(*args):
        pytest.fail("multipart parser must not run")

    sent, reads = asyncio.run(invoke(UploadBoundary(parser, reject_auth), scope(), []))
    assert sent[0]["status"] == 401 and not reads


@pytest.mark.parametrize("length", [None, b"1"])
def test_measured_chunked_or_understated_length_cannot_reach_parser(monkeypatch, length):
    monkeypatch.setenv("FINRISK_MAX_UPLOAD_BYTES", "8")

    async def parser(*args):
        pytest.fail("oversized envelope must not reach multipart parser")

    headers = [] if length is None else [(b"content-length", length)]
    chunks = [{"type": "http.request", "body": b"x" * MULTIPART_OVERHEAD_BYTES, "more_body": True},
              {"type": "http.request", "body": b"x" * 9, "more_body": True}]
    sent, reads = asyncio.run(invoke(UploadBoundary(parser, lambda key: "actor"), scope(headers), chunks))
    assert sent[0]["status"] == 413 and len(reads) == 2


@pytest.mark.parametrize("length,status", [(b"999999", 413), (b"-1", 400), (b"invalid", 400)])
def test_invalid_or_oversized_declared_length_is_rejected_before_receive(monkeypatch, length, status):
    monkeypatch.setenv("FINRISK_MAX_UPLOAD_BYTES", "8")

    async def parser(*args):
        pytest.fail("rejected envelope must not reach parser")

    sent, reads = asyncio.run(invoke(UploadBoundary(parser, lambda key: "actor"),
                                    scope([(b"content-length", length)]), []))
    assert sent[0]["status"] == status and not reads


def test_extra_file_parts_are_bounded_even_when_primary_file_is_small(monkeypatch):
    monkeypatch.setenv("FINRISK_MAX_UPLOAD_BYTES", "8")
    body = (b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n\r\n%PDF\r\n'
            b'--b\r\nContent-Disposition: form-data; name="ignored"; filename="b.pdf"\r\n\r\n'
            + b"x" * MULTIPART_OVERHEAD_BYTES + b"\r\n--b--\r\n")

    async def parser(*args):
        pytest.fail("extra file part must not be spooled")

    sent, _ = asyncio.run(invoke(UploadBoundary(parser, lambda key: "actor"),
                                scope([(b"content-type", b"multipart/form-data; boundary=b")]),
                                [{"type": "http.request", "body": body}]))
    assert sent[0]["status"] == 413


def test_capacity_is_bounded_and_released_on_error(monkeypatch):
    monkeypatch.setenv("FINRISK_MAX_UPLOAD_BYTES", "8")

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()

        async def parser(scope, receive, send):
            assert (await receive())["body"] == b"%PDF"
            started.set()
            await release.wait()
            raise RuntimeError("synthetic parser failure")

        boundary = UploadBoundary(parser, lambda key: "actor", capacity=1)
        first = asyncio.create_task(invoke(boundary, scope(), [{"type": "http.request", "body": b"%PDF"}]))
        await started.wait()
        sent, reads = await invoke(boundary, scope(), [])
        assert sent[0]["status"] == 503 and not reads
        release.set()
        with pytest.raises(RuntimeError, match="synthetic parser failure"):
            await first
        assert not boundary.slots.locked()

    asyncio.run(scenario())


def test_unrelated_requests_keep_original_receive_and_no_upload_auth():
    async def parser(request_scope, receive, send):
        assert (await receive())["body"] == b"hello"
        await send({"type": "http.response.start", "status": 200, "headers": []})

    sent, reads = asyncio.run(invoke(UploadBoundary(parser, reject_auth), scope(path="/api/v1/health"),
                                    [{"type": "http.request", "body": b"hello"}]))
    assert sent[0]["status"] == 200 and len(reads) == 1


@pytest.mark.parametrize("failure", ["configuration", "limiter"])
def test_preparse_failures_keep_503_correlation_and_cors(monkeypatch, failure):
    client = TestClient(api.app)
    credential = client.post("/api/v1/enterprise/organizations", json={
        "name": "Synthetic boundary tenant", "actor_id": "test-admin",
    }).json()["api_key"]
    if failure == "configuration":
        monkeypatch.setenv("FINRISK_MAX_UPLOAD_BYTES", "invalid")
    else:
        def unavailable(key):
            raise RateLimiterUnavailable("synthetic outage")
        monkeypatch.setattr(api.api_limiter, "allow", unavailable)
    response = client.post("/api/v1/documents/analyze", content=b"not parsed",
                           headers={"X-API-Key": credential, "Origin": "http://localhost:3000"})
    assert response.status_code == 503
    assert response.headers["X-Correlation-Id"]
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    if failure == "limiter":
        assert response.headers["Retry-After"] == "5"


def test_empty_frames_do_not_accumulate_retained_memory():
    async def scenario():
        remaining = 100_000

        async def receive():
            nonlocal remaining
            remaining -= 1
            return {"type": "http.request", "body": b"", "more_body": remaining > 0}

        async def parser(request_scope, bounded_receive, send):
            assert (await bounded_receive())["body"] == b""

        async def send(message):
            pass

        boundary = UploadBoundary(parser, lambda key: "actor")
        tracemalloc.start()
        try:
            await boundary(scope(), receive, send)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert peak < 1_000_000

    asyncio.run(scenario())


def test_stalled_upload_times_out_and_releases_capacity(monkeypatch):
    monkeypatch.setattr(module, "UPLOAD_READ_TIMEOUT_SECONDS", .01)

    async def scenario():
        async def receive():
            await asyncio.Event().wait()

        async def parser(*args):
            pytest.fail("stalled upload must not enter parser")

        sent = []

        async def send(message):
            sent.append(message)

        boundary = UploadBoundary(parser, lambda key: "actor", capacity=1)
        await boundary(scope(), receive, send)
        assert sent[0]["status"] == 408 and not boundary.slots.locked()

    asyncio.run(scenario())
