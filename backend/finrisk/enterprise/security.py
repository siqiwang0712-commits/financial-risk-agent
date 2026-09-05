from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from .domain import Principal, Role


@dataclass(frozen=True)
class ApiCredential:
    id: str
    organization_id: str
    key_hash: str
    prefix: str
    user_id: str = "service"
    role: Role = Role.ANALYST
    active: bool = True


def issue_api_key(
    organization_id: str, user_id: str = "service", role: Role = Role.ANALYST
) -> tuple[str, ApiCredential]:
    raw = f"frk_{secrets.token_urlsafe(32)}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return raw, ApiCredential(
        secrets.token_hex(8), organization_id, digest, raw[:8], user_id, role
    )


def verify_api_key(raw: str, credential: ApiCredential) -> bool:
    return credential.active and hmac.compare_digest(
        hashlib.sha256(raw.encode()).hexdigest(), credential.key_hash
    )


class CredentialStore:
    def __init__(self):
        self._credentials: dict[str, ApiCredential] = {}

    def register(self, credential: ApiCredential) -> None:
        self._credentials[credential.prefix] = credential

    def authenticate(self, raw: str) -> Principal:
        credential = self._credentials.get(raw[:8])
        if credential is None or not verify_api_key(raw, credential):
            raise PermissionError("invalid API key")
        return Principal(
            credential.user_id, credential.organization_id, credential.role
        )

    def rotate(self, credential_id: str) -> tuple[str, ApiCredential]:
        current = next(
            (item for item in self._credentials.values() if item.id == credential_id),
            None,
        )
        if current is None:
            raise KeyError(credential_id)
        self._credentials[current.prefix] = ApiCredential(
            **{**current.__dict__, "active": False}
        )
        raw, replacement = issue_api_key(
            current.organization_id, current.user_id, current.role
        )
        self.register(replacement)
        return raw, replacement


class SlidingWindowRateLimiter:
    """Process-local limiter for the prototype API; replace with shared storage at scale."""

    def __init__(self, limit: int = 60, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        events = self._events[key]
        while events and events[0] <= current - self.window_seconds:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(current)
        return True
