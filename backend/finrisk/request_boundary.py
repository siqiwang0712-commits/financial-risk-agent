"""Measured body admission for direct API clients, before JSON/form parsing."""

import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .runtime import positive_env_number


class RequestBodyBoundary:
    def __init__(self, app: ASGIApp, capacity: int = 2, read_timeout: float = 30):
        self.app = app
        self.slots = asyncio.Semaphore(capacity)
        self.read_timeout = read_timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH", "DELETE"}
                or scope.get("path", "").rstrip("/") == "/api/v1/documents/analyze"):
            # PDF uploads retain their authentication-before-read boundary.
            await self.app(scope, receive, send)
            return

        async def reject(status, detail):
            await JSONResponse({"detail": detail}, status)(scope, receive, send)

        try:
            limit = positive_env_number("FINRISK_MAX_REQUEST_BYTES", "52428800", int)
        except RuntimeError:
            await reject(503, "request body limit is not configured safely")
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        if b"content-length" in headers:
            try:
                declared = int(headers[b"content-length"])
                if declared < 0:
                    raise ValueError
            except ValueError:
                await reject(400, "invalid Content-Length")
                return
            if declared > limit:
                await reject(413, "request body-size limit exceeded")
                return
        if self.slots.locked():
            await reject(503, "request body capacity exhausted")
            return
        await self.slots.acquire()
        try:
            buffered = bytearray()
            try:
                async with asyncio.timeout(self.read_timeout):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(buffered) + len(chunk) > limit:
                            await reject(413, "request body-size limit exceeded")
                            return
                        buffered.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await reject(408, "request body read timed out")
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

            await self.app(scope, bounded_receive, send)
        finally:
            self.slots.release()
