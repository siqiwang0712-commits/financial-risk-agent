from __future__ import annotations

import json
import logging
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_logging_configured = False


def configure_logging(level: str | None = None) -> None:
    """Attach a handler to the root logger exactly once.

    Nothing in the project called `basicConfig`/`dictConfig`, so `finrisk.*` INFO
    events propagated to an unconfigured root logger and were discarded by
    `logging.lastResort` (which only emits WARNING and above). A production
    deployment therefore produced no logs whatsoever. Events are emitted as JSON
    on stdout so a collector can parse them; the level is configurable via
    `FINRISK_LOG_LEVEL`.
    """
    global _logging_configured
    if _logging_configured:
        return
    chosen = (level or os.getenv("FINRISK_LOG_LEVEL", "INFO")).upper()
    root = logging.getLogger()
    # Respect logging owned by Uvicorn/Gunicorn, a test runner, or an embedding
    # application.  Replacing root handlers silently disconnects their sinks.
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
        root.setLevel(chosen)
    _logging_configured = True


def bind_correlation_id(value: str | None = None) -> str:
    candidate = (value or "").strip()
    identifier = candidate if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate) else uuid4().hex
    correlation_id.set(identifier)
    return identifier


# Field names whose *values* must never reach the log. Compared after
# `_normalize_field`, so `apiKey`, `api-key`, `API_KEY` and `api_key` all match.
# The set previously held only 4 exact lower-case names, so `apiKey`, `secret`,
# `token`, `password` and `header` were all emitted verbatim.
_FORBIDDEN_FIELDS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "bearer",
        "cookie",
        "credential",
        "credentials",
        "document_text",
        "header",
        "headers",
        "password",
        "passwd",
        "private_key",
        "prompt",
        "raw_text",
        "secret",
        "session",
        "signing_key",
        "token",
        "x_api_key",
    }
)

# Suffixes that make a field credential-bearing whatever its prefix:
# `access_token`, `client_secret`, `refresh_token`, `private_key`, `session_cookie`.
# Redacting a harmless `cache_key` costs a log line; failing to redact an
# `access_token` costs a credential, so this filter fails closed.
_FORBIDDEN_SUFFIXES = (
    "_bearer",
    "_cookie",
    "_credential",
    "_credentials",
    "_key",
    "_passwd",
    "_password",
    "_prompt",
    "_secret",
    "_text",
    "_token",
)


def _normalize_field(name: str) -> str:
    """Fold a field name so camelCase / kebab-case / snake_case / SHOUTING match.

    The previous version inserted `_` before every upper-case letter that was not
    first, which turned `API_KEY` into `a_p_i__key` -- so the four *lower-case*
    names it was built for were the only spellings it ever matched, and an
    all-caps key was logged verbatim. This splits on the camel-case boundary only
    (lower/digit followed by upper), then folds every non-alphanumeric run to `_`.
    """
    text = str(name).strip()
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"[^0-9A-Za-z]+", "_", text)
    return text.strip("_").lower()


def _is_forbidden(name: str) -> bool:
    normalized = _normalize_field(name)
    return normalized in _FORBIDDEN_FIELDS or normalized.endswith(_FORBIDDEN_SUFFIXES)


def structured_event(
    logger: logging.Logger, event: str, level: int = logging.INFO, **safe_fields
) -> None:
    clean = {
        key: value
        for key, value in safe_fields.items()
        if not _is_forbidden(key)
    }
    logger.log(
        level,
        json.dumps(
            {"event": event, "correlation_id": correlation_id.get(), **clean},
            default=str,
        ),
    )


@contextmanager
def traced_stage(logger: logging.Logger, stage: str):
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        # The completion event must not also fire here. A dashboard counting
        # `stage.completed` counted every failure as a success, because the old
        # `finally` emitted it unconditionally after `stage.failed`. Latency is
        # reported on the failure event instead so timing is not lost.
        structured_event(
            logger,
            "stage.failed",
            stage=stage,
            error_type=type(exc).__name__,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        raise
    structured_event(
        logger,
        "stage.completed",
        stage=stage,
        outcome="completed",
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )
