"""Verify the production compose API is ready and uses PostgreSQL persistence.

Run explicitly. Importing this module used to poll for up to 90 seconds and then
raise `SystemExit`, so any tool that imported `scripts/` hung for a minute and a
half.
"""

from __future__ import annotations

import json
import time
from urllib.error import URLError
from urllib.request import urlopen

READINESS_TIMEOUT_SECONDS = 90


def main() -> int:
    deadline = time.monotonic() + READINESS_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen("http://127.0.0.1:8000/health/ready", timeout=3) as response:
                payload = json.load(response)
            if payload.get("status") != "ready":
                raise RuntimeError(f"unexpected readiness status: {payload!r}")
            if payload.get("repository") != "PostgresEnterpriseRepository":
                raise RuntimeError(f"unexpected runtime repository: {payload!r}")
            with urlopen("http://127.0.0.1:3000/api/v1/public-pilot", timeout=5) as response:
                frontend_payload = json.load(response)
            if frontend_payload.get("runtime") != "v0.3.2":
                raise RuntimeError(f"frontend API proxy failed: {frontend_payload!r}")
            print("production compose API is ready with PostgresEnterpriseRepository")
            return 0
        except (OSError, URLError, ValueError, RuntimeError) as exc:
            last_error = exc
            time.sleep(2)
    raise SystemExit(f"production compose readiness failed: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
