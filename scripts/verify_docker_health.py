"""Verify the production compose API is ready and uses PostgreSQL persistence."""

from __future__ import annotations

import json
import time
from urllib.error import URLError
from urllib.request import urlopen

deadline = time.monotonic() + 90
last_error: Exception | None = None
while time.monotonic() < deadline:
    try:
        with urlopen("http://127.0.0.1:8000/health/ready", timeout=3) as response:
            payload = json.load(response)
        if payload.get("status") != "ready":
            raise RuntimeError(f"unexpected readiness status: {payload!r}")
        if payload.get("repository") != "PostgresEnterpriseRepository":
            raise RuntimeError(f"unexpected runtime repository: {payload!r}")
        print("production compose API is ready with PostgresEnterpriseRepository")
        break
    except (OSError, URLError, ValueError, RuntimeError) as exc:
        last_error = exc
        time.sleep(2)
else:
    raise SystemExit(f"production compose readiness failed: {last_error}")
