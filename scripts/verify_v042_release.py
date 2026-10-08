"""Run all local v0.4.2 release gates; never push, tag, dispatch or publish."""

from __future__ import annotations

import argparse
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts import verify_v041_release as gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python311", required=True)
    parser.add_argument("--python312", required=True)
    parser.add_argument("--docker-bin", default="docker")
    parser.add_argument("--npm", default="npm")
    parser.add_argument("--build-network", choices=("default", "host"), default="default")
    parser.add_argument("--build-host", action="append", default=[])
    parser.add_argument("--build-ca-bundle", type=Path)
    parser.add_argument("--build-no-cache", action="store_true")
    args = parser.parse_args()
    gate.STAGE = gate.ROOT / ".runtime/v042-release-gate"
    gate.PROJECT_NAME = "finrisk-v042-release-gate"
    if gate.STAGE.exists():
        shutil.rmtree(gate.STAGE)
    gate.STAGE.mkdir(parents=True)
    gate.run("ruff", [args.python312, "-m", "ruff", "check", "backend", "tests", "scripts", "research"])
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = []
        for number, python in (("311", args.python311), ("312", args.python312)):
            env = {**os.environ, "COVERAGE_FILE": str(gate.STAGE / f".coverage-{number}")}
            database = os.getenv(f"FINRISK_GATE_DATABASE_URL{number}", os.getenv("DATABASE_URL"))
            if not database:
                raise SystemExit("real PostgreSQL DATABASE_URL is required for the release gate")
            env["DATABASE_URL"] = database
            futures.append(executor.submit(gate.python_gate, python, f"Python 3.{number[-2:]}", env))
        for future in futures:
            future.result()
    gate.research_and_docs_gate(args.python312, "scripts.verify_v042")
    gate.frontend_gate(args.npm)
    gate.package_gate(args.python311, args.python312, "0.4.2")
    build_options = ["--network", args.build_network]
    if args.build_no_cache:
        build_options.append("--no-cache")
    for host in args.build_host:
        build_options.extend(("--add-host", host))
    if args.build_ca_bundle:
        build_options.extend(("--secret", f"id=finrisk_ca_bundle,src={args.build_ca_bundle.resolve()}"))
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        if os.getenv(name):
            build_options.extend(("--build-arg", name))
            os.environ.setdefault(name.lower(), os.environ[name])
            build_options.extend(("--build-arg", name.lower()))
    gate.container_gate(args.docker_bin, args.python312, "0.4.2", build_options)
    gate.run("whitespace", ["git", "diff", "HEAD", "--check"])
    print("LOCAL v0.4.2 RELEASE GATE: PASS")
    print("Remote ordinary CI and publish=false container dry-run must be verified separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
