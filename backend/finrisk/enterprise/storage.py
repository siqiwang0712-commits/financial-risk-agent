from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredDocument:
    organization_id: str
    object_id: str
    sha256: str
    size: int


class DocumentStorage(Protocol):
    def put(
        self, organization_id: str, object_id: str, content: bytes
    ) -> StoredDocument: ...

    def get(self, organization_id: str, object_id: str) -> bytes: ...


class LocalDocumentStorage:
    """Tenant-scoped local adapter; production deployments can supply object storage."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    @staticmethod
    def _safe(value: str) -> str:
        if not value or any(token in value for token in ("..", "/", "\\")):
            raise ValueError("unsafe storage identifier")
        return value

    def _path(self, organization_id: str, object_id: str) -> Path:
        return self.root / self._safe(organization_id) / self._safe(object_id)

    def put(
        self, organization_id: str, object_id: str, content: bytes
    ) -> StoredDocument:
        path = self._path(organization_id, object_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return StoredDocument(
            organization_id,
            object_id,
            hashlib.sha256(content).hexdigest(),
            len(content),
        )

    def get(self, organization_id: str, object_id: str) -> bytes:
        return self._path(organization_id, object_id).read_bytes()
