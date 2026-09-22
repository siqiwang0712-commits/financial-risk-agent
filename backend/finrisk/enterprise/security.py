from __future__ import annotations

import hashlib
import hmac
import os
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


class RateLimiterUnavailable(RuntimeError):
    """The limiter could not decide, because its backing store is unavailable.

    Callers must fail *closed*: an admission decision that cannot be made is not an
    admission. Surfacing a distinct type lets the API answer a controlled 503
    instead of letting a driver error escape as an unhandled 500 — and, crucially,
    instead of silently letting the request through unthrottled.
    """


#: Advisory-lock key for the periodic retention sweep. Replicas compete for it so
#: only one of them runs the sweep at a time.
_SWEEP_LOCK_KEY = 4_242_001


class PostgresRateLimiter:
    """Shared sliding-window limiter backed by the database.

    Same `allow(key)` contract as the in-process fallback, but the window lives in
    `rate_limit_events`, so the bound survives a restart and is shared by every
    replica. `SlidingWindowRateLimiter` remains for local/in-memory runs.

    The per-key prune alone left the table growing forever: it only ever removed the
    rows belonging to the key being checked, so an attacker who varied the key (the
    bootstrap limiter keys on the client, so rotating source addresses does it) left
    one stale row set per key behind. A bounded global retention runs alongside the
    per-key window: expired rows are swept in bounded batches at most once per window.

    The row cap is a *fail-closed* bound, not a trimming one. It used to delete the
    oldest surviving rows to stay under the cap, which deleted events that were still
    inside their window — a key that had genuinely exhausted its quota silently got
    its quota back early, and a flood of unique keys could keep resetting that for
    free. Now the cap only ever refuses admission: expired rows are removed, and if
    what remains still fills the table there is nowhere safe to put a new event, so
    the limiter says so (`RateLimiterUnavailable` → controlled 503) instead of
    quietly dropping the live evidence that constrains a client.
    """

    def __init__(
        self,
        connection_or_repository,
        limit: int = 60,
        window_seconds: int = 60,
        *,
        max_rows: int | None = None,
        retention_factor: float = 2.0,
        sweep_batch_size: int = 1_000,
        sweep_batches: int = 10,
    ):
        self.resource = connection_or_repository
        self.limit = limit
        self.window_seconds = window_seconds
        # Anything older than two windows can never influence a decision, so it is
        # always safe to drop; the cap bounds the pathological case where a flood of
        # unique keys arrives inside a single window.
        self.retention_seconds = max(float(window_seconds) * retention_factor, 1.0)
        self.max_rows = (
            max_rows
            if max_rows is not None
            else int(os.getenv("FINRISK_RATE_LIMIT_MAX_ROWS", "200000"))
        )
        self.sweep_batch_size = sweep_batch_size
        self.sweep_batches = sweep_batches
        self._last_sweep = 0.0
        self._lock = Lock()

    @contextmanager
    def _connection(self):
        if hasattr(self.resource, "connection_context"):
            with self.resource.connection_context() as connection:
                yield connection
        else:
            yield self.resource

    def _sweep_due(self, current: float) -> bool:
        if current - self._last_sweep < float(self.window_seconds):
            return False
        self._last_sweep = current
        return True

    def _sweep(self, cursor) -> None:
        """Drop expired rows only, in bounded batches.

        Nothing here may delete a row that is still inside its window: those rows are
        the record of what a client has already spent, and removing them restores a
        quota that was legitimately exhausted. Capacity is handled by refusing
        admission (`allow`), never by discarding live evidence.
        """
        for _ in range(self.sweep_batches):
            cursor.execute(
                """DELETE FROM rate_limit_events
                   WHERE ctid IN (
                       SELECT ctid FROM rate_limit_events
                       WHERE occurred_at < now() - make_interval(secs => %s)
                       LIMIT %s
                   )""",
                (float(self.retention_seconds), self.sweep_batch_size),
            )
            if cursor.rowcount < self.sweep_batch_size:
                break

    def allow(self, key: str, now: float | None = None) -> bool:
        # `now` is accepted for contract parity with the fallback; the shared window
        # is anchored to the database clock so replicas cannot disagree about it.
        scope = "api"
        try:
            with self._lock, self._connection() as connection:
                with connection.cursor() as cursor:
                    if self._sweep_due(time.monotonic()):
                        # Best effort: if another replica holds the sweep lock, this
                        # one skips it rather than queueing behind it.
                        cursor.execute(
                            "SELECT pg_try_advisory_xact_lock(%s)", (_SWEEP_LOCK_KEY,)
                        )
                        if cursor.fetchone()[0]:
                            self._sweep(cursor)
                    # Serialise per key so two replicas cannot both read "under the
                    # limit" and both admit. The lock is transaction-scoped.
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{scope}:{key}",)
                    )
                    # Prune and count as separate statements. A single statement with
                    # a data-modifying CTE does *not* work here: every part of one
                    # statement shares a snapshot, so the count would still see the
                    # rows the DELETE just removed — the window would never drain and
                    # the first request after a quiet period was wrongly rejected.
                    cursor.execute(
                        """DELETE FROM rate_limit_events
                           WHERE scope = %s AND key = %s
                             AND occurred_at < now() - make_interval(secs => %s)""",
                        (scope, key, float(self.window_seconds)),
                    )
                    # Capacity is checked against *live* rows, not against the whole
                    # table: expired rows that a sweep has not reached yet are not
                    # occupying anyone's quota, and counting them would refuse
                    # requests for a table that is merely due for a clean-up. Counting
                    # live rows also means recovery is automatic — as soon as rows age
                    # out of the retention window the capacity is theirs again, with
                    # no sweep having to win the lock first.
                    live_total = 0
                    if self.max_rows > 0:
                        cursor.execute(
                            """SELECT count(*) FROM rate_limit_events
                               WHERE occurred_at >= now() - make_interval(secs => %s)""",
                            (float(self.retention_seconds),),
                        )
                        live_total = cursor.fetchone()[0]
                        if live_total >= self.max_rows:
                            # Nothing safe can be deleted to make room, so the only
                            # honest answers are "refuse" or "admit while dropping the
                            # rows that constrain other clients". Refuse: the API
                            # turns this into a controlled 503 with `Retry-After`.
                            raise RateLimiterUnavailable(
                                "rate limiter store is at capacity; "
                                "no expired events to reclaim"
                            )
                    cursor.execute(
                        "SELECT count(*) FROM rate_limit_events WHERE scope = %s AND key = %s",
                        (scope, key),
                    )
                    live_for_key = cursor.fetchone()[0]
                    admitted = live_for_key < int(self.limit)
                    # A flood of never-before-seen keys is how the shared table is
                    # driven to capacity: each one inserts a single row that the
                    # per-key prune can never reclaim, and once the table is full
                    # *every* client is refused. Stop admitting novel keys well before
                    # that point, so clients that already hold a window keep being
                    # served and the table never reaches the cliff.
                    if (
                        admitted
                        and live_for_key == 0
                        and self.max_rows > 0
                        and live_total >= self.max_rows // 2
                    ):
                        raise RateLimiterUnavailable(
                            "rate limiter store is under pressure; new keys are not "
                            "admitted until existing windows expire"
                        )
                    if admitted:
                        cursor.execute(
                            "INSERT INTO rate_limit_events (scope, key, occurred_at) VALUES (%s, %s, now())",
                            (scope, key),
                        )
                connection.commit()
        except RateLimiterUnavailable:
            raise
        except Exception as exc:
            # Fail closed and distinctly. Letting the driver error escape produced an
            # unhandled 500; treating it as "allowed" would silently disable the only
            # protection the unauthenticated bootstrap route has.
            raise RateLimiterUnavailable(
                f"rate limiter store unavailable: {type(exc).__name__}"
            ) from exc
        return bool(admitted)


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
        try:
            role = Role(row[4])
        except ValueError as exc:
            # A row with an unrecognised role is a credential problem, not a server
            # fault: `authenticated_principal` only catches PermissionError, so
            # anything else escaped as an opaque 500 on every request.
            raise PermissionError("invalid API key") from exc
        credential = ApiCredential(row[0], row[1], row[2], prefix, row[3], role, row[5])
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
