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
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.handlers = [handler]
    root.setLevel(chosen)
    _logging_configured = True


def bind_correlation_id(value: str | None = None) -> str:
    candidate = (value or "").strip()
    identifier = candidate if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate) else uuid4().hex
    correlation_id.set(identifier)
    return identifier


# Substring rules, not an exact-match set. The previous allowlist of four literal
# names let `x-api-key`, `Authorization`, `openai_api_key`, `database_url`,
# `password` and `token` through unredacted; today's call sites happen not to pass
# them, which is luck rather than design.
_SENSITIVE_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "database_url",
    "document_text",
    "password",
    "prompt",
    "secret",
    "token",
)
_SENSITIVE_EXACT = {"key", "auth"}


def is_sensitive_field(name: str) -> bool:
    lowered = name.lower()
    if lowered in _SENSITIVE_EXACT:
        return True
    return any(marker in lowered for marker in _SENSITIVE_MARKERS)


def structured_event(
    logger: logging.Logger, event: str, level: int = logging.INFO, **safe_fields
) -> None:
    clean = {
        key: value
        for key, value in safe_fields.items()
        if not is_sensitive_field(key)
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
        structured_event(
            logger, "stage.failed", stage=stage, error_type=type(exc).__name__
        )
        raise
    finally:
        structured_event(
            logger,
            "stage.completed",
            stage=stage,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
