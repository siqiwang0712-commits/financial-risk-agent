"""Runtime configuration and dependency assembly for the HTTP application."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from .enterprise.postgres import PostgresEnterpriseRepository
from .enterprise.repository import InMemoryEnterpriseRepository
from .enterprise.security import CredentialStore, PostgresCredentialStore
from .enterprise.service import EnterpriseRiskService
from .secret_files import env_or_file

Number = TypeVar("Number", int, float)


@dataclass(frozen=True, slots=True)
class RuntimeComponents:
    service: EnterpriseRiskService
    credentials: CredentialStore | PostgresCredentialStore


@dataclass(frozen=True, slots=True)
class DocumentLimits:
    upload_bytes: int
    pages: int
    extracted_chars: int
    timeout_seconds: float


def positive_env_number(
    name: str,
    default: str,
    cast: Callable[[str], Number],
) -> Number:
    raw = os.getenv(name, default)
    try:
        value = cast(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive number")
    return value


def max_upload_bytes() -> int:
    """Return the upload ceiling shared with the Next proxy."""
    if os.getenv("FINRISK_MAX_UPLOAD_BYTES"):
        return int(
            positive_env_number("FINRISK_MAX_UPLOAD_BYTES", "52428800", int)
        )
    return int(positive_env_number("FINRISK_MAX_UPLOAD_MB", "50", int)) * 1024 * 1024


def document_limits() -> DocumentLimits:
    return DocumentLimits(
        upload_bytes=max_upload_bytes(),
        pages=int(positive_env_number("FINRISK_MAX_PDF_PAGES", "500", int)),
        extracted_chars=int(
            positive_env_number("FINRISK_MAX_EXTRACTED_CHARS", "5000000", int)
        ),
        timeout_seconds=float(
            positive_env_number("FINRISK_ANALYSIS_TIMEOUT_SECONDS", "60", float)
        ),
    )


def build_runtime_components(root: Path) -> RuntimeComponents:
    database_url = env_or_file("DATABASE_URL")
    environment = os.getenv("FINRISK_ENV", "development").lower()
    if environment == "production" and (
        not database_url or "local-development-only" in database_url
    ):
        raise RuntimeError(
            "production requires an explicit DATABASE_URL with a non-default password"
        )
    if database_url:
        repository = PostgresEnterpriseRepository.connect(database_url)
        if os.getenv("FINRISK_AUTO_MIGRATE", "0") == "1":
            for migration in sorted((root / "migrations").glob("*.sql")):
                repository.migrate(migration)
        credentials = PostgresCredentialStore(repository)
    else:
        repository = InMemoryEnterpriseRepository()
        credentials = CredentialStore()
    return RuntimeComponents(
        service=EnterpriseRiskService(repository),
        credentials=credentials,
    )
