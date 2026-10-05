"""Authenticate and bound PDF requests before FastAPI parses multipart files."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .enterprise.security import RateLimiterUnavailable
from .runtime import max_upload_bytes

MULTIPART_OVERHEAD_BYTES = 64 * 1024  # Same framing allowance as the Next proxy.
UPLOAD_PRINCIPAL = "finrisk_upload_principal"
UPLOAD_READ_TIMEOUT_SECONDS = 30


class UploadBoundary:
    def __init__(self, app: ASGIApp, authenticate: Callable, capacity: int = 2):
        self.app = app
        self.authenticate = authenticate
        self.slots = asyncio.Semaphore(capacity)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http" or scope.get("method") != "POST"
                or scope.get("path", "").rstrip("/") != "/api/v1/documents/analyze"):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_key = headers.get(b"x-api-key")
        try:
            principal = await run_in_threadpool(
                self.authenticate, raw_key.decode("latin-1") if raw_key else None,
            )
        except HTTPException as exc:
            await JSONResponse({"detail": exc.detail}, exc.status_code, headers=exc.headers)(scope, receive, send)
            return
        except RateLimiterUnavailable:
            await JSONResponse({"detail": "rate limiter temporarily unavailable"}, 503,
                               headers={"Retry-After": "5"})(scope, receive, send)
            return
        if self.slots.locked():
            await JSONResponse({"detail": "document upload capacity exhausted"}, 503,
                               headers={"Retry-After": "1"})(scope, receive, send)
            return
        await self.slots.acquire()
        try:
            try:
                limit = max_upload_bytes() + MULTIPART_OVERHEAD_BYTES
            except RuntimeError:
                await JSONResponse({"detail": "document limits are not configured safely"}, 503)(scope, receive, send)
                return
            declared = headers.get(b"content-length")
            if declared is not None:
                try:
                    length = int(declared)
                    if length < 0:
                        raise ValueError
                except ValueError:
                    await JSONResponse({"detail": "invalid Content-Length"}, 400)(scope, receive, send)
                    return
                if length > limit:
                    await self._too_large(scope, receive, send)
                    return
            # Buffer only a bounded envelope, before *any* multipart parser runs.
            # Count measured bytes even for absent, dishonest or chunked lengths.
            buffered = bytearray()
            try:
                async with asyncio.timeout(UPLOAD_READ_TIMEOUT_SECONDS):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(buffered) + len(chunk) > limit:
                            await self._too_large(scope, receive, send)
                            return
                        buffered.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await JSONResponse({"detail": "document upload timed out"}, 408)(scope, receive, send)
                return
            body = bytes(buffered)
            buffered.clear()
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            scope.setdefault("state", {})[UPLOAD_PRINCIPAL] = principal
            await self.app(scope, bounded_receive, send)
        finally:
            scope.get("state", {}).pop(UPLOAD_PRINCIPAL, None)
            self.slots.release()

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse({"detail": "multipart upload-size limit exceeded"}, 413)(scope, receive, send)
