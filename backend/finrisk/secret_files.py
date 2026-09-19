"""Reading a secret from a mounted file (`<NAME>_FILE`) or from the environment.

Shared by the API process and by the migration job that gates every production
deploy, so both resolve a secret the same way — an operator who mounts
`DATABASE_URL` as a file must not end up with an API that reads the file and a
migration that reads a stale environment value.
"""

from __future__ import annotations

import os
from pathlib import Path


def env_or_file(name: str) -> str | None:
    """Read a secret from `<NAME>_FILE` (Docker/K8s secret mount) or from the env.

    Preferring the file form keeps secrets out of `docker inspect` output and out
    of the process environment, which is visible to any child process.

    Failure is *loud*, never silent: a configured-but-unreadable `<NAME>_FILE` raises
    instead of quietly falling back to `<NAME>`, because a fallback would either
    disable the protection (an unread bootstrap token) or connect to the wrong
    database while appearing healthy. Only an absent variable or an empty file falls
    back. Neither the path nor the content is logged.
    """
    path = os.getenv(f"{name}_FILE")
    if path:
        try:
            content = Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(
                f"{name}_FILE is set but could not be read; refusing to fall back to {name}"
            ) from exc
        if content:
            return content
    value = os.getenv(name)
    return value or None
