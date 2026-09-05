from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def bind_correlation_id(value: str | None = None) -> str:
    identifier = value or uuid4().hex
    correlation_id.set(identifier)
    return identifier


def structured_event(logger: logging.Logger, event: str, **safe_fields) -> None:
    forbidden = {"api_key", "authorization", "document_text", "prompt"}
    clean = {
        key: value for key, value in safe_fields.items() if key.lower() not in forbidden
    }
    logger.info(
        json.dumps(
            {"event": event, "correlation_id": correlation_id.get(), **clean},
            default=str,
        )
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
