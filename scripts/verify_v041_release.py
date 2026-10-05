"""Run the complete local v0.4.1 release gate.

The command intentionally includes slow interpreter, package, frontend, research, and
container checks. It never pushes, tags, publishes, or creates a release.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / ".runtime" / "v041-release-gate"


def run(
    label: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> None:
    print(f"\n== {label} ==", flush=True)
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode:
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def wait_http(url: str, timeout: float = 180) -> None:
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=3) as response:
                if response.status == 200:
                    return
        except (OSError, URLError, ValueError) as exc:
            last = exc
        time.sleep(2)
    raise SystemExit(f"HTTP endpoint did not stabilize: {url}: {last}")


def compose(docker: str, files: list[str], *args: str) -> list[str]:
    # All volumes removed by this gate belong to this disposable test project,
    # never the operator's default Compose project.
    command = [docker, "compose", "--project-name", "finrisk-v041-release-gate"]
    for filename in files:
        command.extend(("-f", filename))
    return [*command, *args]


def python_gate(python: str, label: str) -> None:
    expected = [3, int(label.rsplit(".", 1)[1])]
    actual = json.loads(subprocess.check_output(
        [python, "-c", "import json,sys; print(json.dumps(list(sys.version_info[:2])))"],
        text=True,
    ))
    if actual != expected:
        raise SystemExit(f"{label} requires {expected}, supplied interpreter is {actual}")
    run(f"{label} dependency consistency", [python, "-m", "pip", "check"])
    run(
        f"{label} locked dependency security audit",
        [python, "-m", "pip_audit", "--strict", "--no-deps", "-r", "requirements.lock"],
    )
    run(
        f"{label} backend tests and coverage",
        [
            python,
            "-m",
            "pytest",
            "--cov=finrisk",
            "--cov-report=term-missing",
            f"--cov-report=json:{STAGE / ('coverage-' + label[-4:].replace('.', '') + '.json')}",
            "--cov-fail-under=90",
            "-o",
            f"cache_dir={STAGE / 'pytest-cache'}",
            f"--junitxml={STAGE / ('tests-' + label[-4:].replace('.', '') + '.xml')}",
            "--basetemp",
            str(STAGE / f"pytest-{label.lower().replace(' ', '-') }"),
        ],
    )


def package_gate(python311: str, python312: str) -> None:
    dist = STAGE / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    for artifact in (*dist.glob("finrisk_agent-*.whl"), *dist.glob("finrisk_agent-*.tar.gz")):
        artifact.unlink()
    run("build wheel and sdist", [python311, "-m", "build", "--outdir", str(dist)])
    wheels = list(dist.glob("finrisk_agent-0.4.1-*.whl"))
    archives = list(dist.glob("finrisk_agent-0.4.1.tar.gz"))
    if len(wheels) != 1 or len(archives) != 1:
        raise SystemExit("package build did not produce exactly one v0.4.1 wheel and sdist")
    for label, python in (("Python 3.11", python311), ("Python 3.12", python312)):
        venv = STAGE / f"wheel-venv-{label[-4:].replace('.', '')}"
        if venv.exists():
            shutil.rmtree(venv)
        run(f"create clean package environment ({label})", [python, "-m", "venv", str(venv)])
        installed = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(
            f"install wheel ({label})",
            [
                str(installed),
                "-m",
                "pip",
                "install",
                "-c",
                str(ROOT / "requirements.lock"),
                str(wheels[0]),
            ],
        )
        run(f"installed dependency consistency ({label})", [str(installed), "-m", "pip", "check"])
        with tempfile.TemporaryDirectory(prefix="finrisk-wheel-smoke-") as isolated:
            run(
                f"installed package/API/Assurance/certificate smoke ({label})",
                [str(installed), str(ROOT / "scripts" / "verify_installed_package.py")],
                env={**os.environ, "FINRISK_LLM_PROVIDER": "mock", "PYTHONPATH": ""},
                cwd=Path(isolated),
            )


def research_and_docs_gate(python: str) -> None:
    run("v0.4.1 checked-in artifact gate", [python, "scripts/verify_v041.py"])
    run("frozen E4 public artifacts", [python, "scripts/verify_e4_public_artifacts.py"])
    run(
        "E4-S independent audit",
        [
            python,
            "research/e4_statistical_audit/verify_audit.py",
            "--quick",
            "--out",
            str(STAGE / "e4s-verification.json"),
        ],
    )
    run("E4-R integrity and reproduction", [python, "research/e4r_automated_robustness/verify_e4r.py"])
    run(
        "E5 remains NOT_FROZEN",
        [python, "research/e5/protocol/verify_freeze_chain.py", "--report-only"],
    )
    run("demo fixture reproducibility", [python, "scripts/generate_demo_fixture.py", "--check"])
    run(
        "development reference reproducibility",
        [python, "scripts/generate_v040_development_reference.py", "--check"],
    )
    run("Markdown link integrity", [python, "scripts/check_markdown_links.py"])


def frontend_gate(npm: str) -> None:
    run("frontend clean dependency install", [npm, "--prefix", "frontend", "ci"])
    run("frontend production dependency audit", [npm, "--prefix", "frontend", "audit", "--omit=dev", "--audit-level=high"])
    for task in ("test", "lint", "typecheck", "build"):
        run(f"frontend {task}", [npm, "--prefix", "frontend", "run", task])


def container_gate(docker: str, python: str) -> None:
    common = {
        **os.environ,
        "FINRISK_LLM_PROVIDER": "mock",
        "NO_PROXY": "localhost,127.0.0.1,::1",
        "no_proxy": "localhost,127.0.0.1,::1",
        "PYTHONPATH": "backend",
    }
    development = ["docker-compose.yml", "docker-compose.prod.yml"]
    release = ["docker-compose.release.yml"]
    dev_env = {
        **common,
        "POSTGRES_PASSWORD": "v041-gate-development-password",
        "FINRISK_BOOTSTRAP_TOKEN": "v041-gate-development-bootstrap",
    }
    release_env = {
        **common,
        "POSTGRES_PASSWORD": "v041-gate-release-password",
        "FINRISK_BOOTSTRAP_TOKEN": "v041-gate-release-bootstrap",
        "FINRISK_API_IMAGE": "finrisk-v041-gate-api:candidate",
        "FINRISK_WEB_IMAGE": "finrisk-v041-gate-web:candidate",
    }
    subprocess.run(compose(docker, release, "down", "-v"), cwd=ROOT, env=release_env, check=False)
    subprocess.run(compose(docker, development, "down", "-v"), cwd=ROOT, env=dev_env, check=False)
    try:
        run(
            "build release API candidate",
            [docker, "build", "-f", "backend/Dockerfile", "-t", release_env["FINRISK_API_IMAGE"], "."],
            env=release_env,
        )
        run(
            "build release web candidate",
            [docker, "build", "-f", "frontend/Dockerfile", "-t", release_env["FINRISK_WEB_IMAGE"], "frontend"],
            env=release_env,
        )
        run("development Compose build/start", compose(docker, development, "up", "--build", "-d", "postgres", "migrate", "api", "web"), env=dev_env)
        wait_http("http://127.0.0.1:8000/health/ready")
        wait_http("http://127.0.0.1:8000/health/live")
        run("development container HTTP contracts", [python, "scripts/verify_docker_health.py"], env=dev_env)
        dev_state = STAGE / "development-postgres.json"
        run("development PostgreSQL before restart", [python, "scripts/verify_postgres_state.py", "--phase", "before", "--state-file", str(dev_state)], env=dev_env)
        run("development API restart", compose(docker, development, "restart", "api"), env=dev_env)
        wait_http("http://127.0.0.1:8000/health/ready")
        run("development PostgreSQL after restart", [python, "scripts/verify_postgres_state.py", "--phase", "after", "--state-file", str(dev_state)], env=dev_env)
        run("stop development Compose", compose(docker, development, "down", "-v"), env=dev_env)

        run("release Compose configuration", compose(docker, release, "config", "--quiet"), env=release_env)
        run("release Compose start", compose(docker, release, "up", "-d", "postgres", "migrate", "api", "web"), env=release_env)
        wait_http("http://127.0.0.1:8000/health/ready")
        wait_http("http://127.0.0.1:8000/health/live")
        run("release container HTTP contracts", [python, "scripts/verify_docker_health.py"], env=release_env)
        postgres_env = {
            **release_env,
            "DATABASE_URL": "postgresql://finrisk:v041-gate-release-password@127.0.0.1:55432/finrisk",
        }
        run("PostgreSQL migration idempotence", [python, "scripts/validate_postgres_migration.py"], env=postgres_env)
        run("PostgreSQL integration tests", [python, "-m", "pytest", "tests/test_postgres_runtime.py", "-q", "--basetemp", str(STAGE / "pytest-postgres")], env=postgres_env)
        release_state = STAGE / "release-postgres.json"
        run("release PostgreSQL before restart", [python, "scripts/verify_postgres_state.py", "--phase", "before", "--state-file", str(release_state)], env=release_env)
        run("release API restart", compose(docker, release, "restart", "api"), env=release_env)
        wait_http("http://127.0.0.1:8000/health/ready")
        run("release PostgreSQL after restart", [python, "scripts/verify_postgres_state.py", "--phase", "after", "--state-file", str(release_state)], env=release_env)
        timeout_env = {**release_env, "FINRISK_ANALYSIS_TIMEOUT_SECONDS": "0.001"}
        run("recreate timeout path", compose(docker, release, "up", "-d", "--force-recreate", "api", "web"), env=timeout_env)
        wait_http("http://127.0.0.1:8000/health/ready")
        run("production timeout/retry contract", [python, "scripts/verify_docker_timeout.py"], env=timeout_env)
    finally:
        subprocess.run(compose(docker, release, "down", "-v"), cwd=ROOT, env=release_env, check=False)
        subprocess.run(compose(docker, development, "down", "-v"), cwd=ROOT, env=dev_env, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python311", required=True)
    parser.add_argument("--python312", required=True)
    parser.add_argument("--docker-bin", required=True)
    parser.add_argument("--npm", default=shutil.which("npm.cmd") or shutil.which("npm") or "npm")
    args = parser.parse_args()

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    run("ruff", [args.python311, "-m", "ruff", "check", "backend", "tests", "scripts", "research"])
    python_gate(args.python311, "Python 3.11")
    python_gate(args.python312, "Python 3.12")
    # The fitted StrongTabularReference pickle is replayable only in its pinned
    # Python 3.12 numeric runtime. Product tests still run under both supported
    # interpreters above; using 3.11 here must fail closed rather than silently
    # relaxing the artifact's runtime identity.
    research_and_docs_gate(args.python312)
    frontend_gate(args.npm)
    package_gate(args.python311, args.python312)
    container_gate(args.docker_bin, args.python311)
    run("working-tree whitespace", ["git", "diff", "HEAD", "--check"])
    print("\nLOCAL RELEASE GATE: PASS")
    print("FINAL REMOTE CONTAINER RELEASE DRY-RUN REQUIRED (version=v0.4.1, publish=false)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
