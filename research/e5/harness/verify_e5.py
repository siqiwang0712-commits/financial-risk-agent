"""One-command verification of the E5 staged freeze chain.

    python research/e5/harness/verify_e5.py

Exit code 0 when every recorded check passes, 1 otherwise. Stages that have not been
frozen yet are reported as absent rather than treated as failures, so the command is
safe to run in CI long before the study executes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from e5_harness import main

if __name__ == "__main__":
    raise SystemExit(main())
