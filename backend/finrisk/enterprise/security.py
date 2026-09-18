from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import OrderedDict, deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol

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
    credential_id = secrets.token_hex(16)
    prefix = f"frk_{credential_id}"
    raw = f"{prefix}_{secrets.token_urlsafe(32)}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return raw, ApiCredential(
        credential_id, organization_id, digest, prefix, user_id, role
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
        prefix = "_".join(raw.split("_", 2)[:2])
        credential = self._credentials.get(prefix)
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


class DurableCredentialStore(Protocol):
    def register(self, credential: ApiCredential) -> None: ...
    def authenticate(self, raw: str) -> Principal: ...
    def rotate(self, credential_id: str) -> tuple[str, ApiCredential]: ...


class PostgresCredentialStore:
    """Durable credentials; only hashes and non-secret identifiers are persisted."""

    def __init__(self, connection_or_repository):
        self.resource = connection_or_repository

    @contextmanager
    def _connection(self):
        if hasattr(self.resource, "connection_context"):
            with self.resource.connection_context() as connection:
                yield connection
        else:
            yield self.resource

    def register(self, credential: ApiCredential) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                self._insert(cursor, credential)
            connection.commit()

    @staticmethod
    def _insert(cursor, credential: ApiCredential) -> None:
        cursor.execute(
            """INSERT INTO api_credentials
            (id,credential_prefix,organization_id,user_id,role,secret_hash,active)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (credential.id, credential.prefix, credential.organization_id,
             credential.user_id, credential.role.value, credential.key_hash,
             credential.active),
        )

    def authenticate(self, raw: str) -> Principal:
        prefix = "_".join(raw.split("_", 2)[:2])
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,organization_id,secret_hash,user_id,role,active FROM api_credentials WHERE credential_prefix=%s",
                (prefix,),
            )
            row = cursor.fetchone()
        if row is None:
            raise PermissionError("invalid API key")
        credential = ApiCredential(row[0], row[1], row[2], prefix, row[3], Role(row[4]), row[5])
        if not verify_api_key(raw, credential):
            raise PermissionError("invalid API key")
        return Principal(credential.user_id, credential.organization_id, credential.role)

    def rotate(self, credential_id: str) -> tuple[str, ApiCredential]:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT organization_id,user_id,role FROM api_credentials WHERE id=%s AND active=true FOR UPDATE",
                    (credential_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(credential_id)
                raw, replacement = issue_api_key(row[0], row[1], Role(row[2]))
                cursor.execute(
                    "UPDATE api_credentials SET active=false,revoked_at=%s WHERE id=%s",
                    (datetime.now(UTC), credential_id),
                )
                self._insert(cursor, replacement)
            connection.commit()
        return raw, replacement


class RateLimiter(Protocol):
    def allow(self, key: str, now: float | None = None) -> bool: ...


class SlidingWindowRateLimiter:
    """Development fallback implementing the shared-store-ready limiter contract.

    Keys are bounded so an attacker cannot grow `_events` without limit (e.g. by
    creating unbounded organizations through the bootstrap endpoint). The least
    recently active key is evicted once `max_keys` is reached.
    """

    def __init__(self, limit: int = 60, window_seconds: int = 60, max_keys: int = 10_000):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        # Insertion-ordered so eviction is O(1); a `min()` scan over every key ran
        # on every request once `max_keys` was reached.
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    def _evict_if_needed(self, key: str) -> None:
        if key in self._events or len(self._events) < self.max_keys:
            return
        self._events.popitem(last=False)

    def allow(self, key: str, now: float | None = None) -> bool:
        # The fallback is process-local by design, but it must still be correct
        # under FastAPI's concurrent worker threads.
        with self._lock:
            current = time.monotonic() if now is None else now
            self._evict_if_needed(key)
            events = self._events.get(key)
            if events is None:
                events = self._events[key] = deque()
            self._events.move_to_end(key)
            while events and events[0] <= current - self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(current)
            return True
