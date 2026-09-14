from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Storage identifiers are opaque and generated (`new_id` produces `prefix_hex`),
# so an allowlist is both sufficient and much harder to defeat than the previous
# deny-list of `..`, `/` and `\`. That deny-list missed:
#   * `C:evil` - `pathlib` rewrites a drive-relative component, so on Windows
#     `root / "C:evil"` resolves under `root` as `evil`, and the stored
#     `StoredDocument.object_id` no longer names the file on disk;
#   * `a\x00b` - truncated at the NUL on POSIX, so two distinct ids mapped to one
#     file;
#   * anything else the OS treats specially.
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,127}")


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
        if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("unsafe storage identifier")
        return value

    def _path(self, organization_id: str, object_id: str) -> Path:
        path = self.root / self._safe(organization_id) / self._safe(object_id)
        # Belt and braces: even with an allowlisted identifier, refuse anything
        # that does not resolve underneath the storage root.
        resolved = path.resolve()
        if self.root != resolved and self.root not in resolved.parents:
            raise ValueError("unsafe storage identifier")
        return resolved

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
