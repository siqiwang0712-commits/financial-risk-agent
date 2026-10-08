"""Run the complete local v0.4.1 release gate.

The command intentionally includes slow interpreter, package, frontend, research, and
container checks. It never pushes, tags, publishes, or creates a release.
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
PROJECT_NAME = "finrisk-v041-release-gate"


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
    command = [docker, "compose", "--project-name", PROJECT_NAME]
    for filename in files:
        command.extend(("-f", filename))
    return [*command, *args]


def verify_container_identities(
    docker: str, files: list[str], env: dict[str, str], identities: dict[str, str],
) -> None:
    for service in ("api", "web", "migrate"):
        container = subprocess.check_output(
            compose(docker, files, "ps", "-q", "-a", service), env=env, text=True,
        ).strip()
        actual = subprocess.check_output(
            [docker, "inspect", "--format", "{{.Image}}", container], env=env, text=True,
        ).strip()
        if actual != identities["api" if service == "migrate" else service]:
            raise SystemExit(f"{service} does not run the verified candidate artifact")


def python_gate(python: str, label: str, env: dict[str, str] | None = None) -> None:
    expected = [3, int(label.rsplit(".", 1)[1])]
    actual = json.loads(subprocess.check_output(
        [python, "-c", "import json,sys; print(json.dumps(list(sys.version_info[:2])))"],
        text=True,
    ))
    if actual != expected:
        raise SystemExit(f"{label} requires {expected}, supplied interpreter is {actual}")
    options = {"env": env} if env is not None else {}
    run(f"{label} dependency consistency", [python, "-m", "pip", "check"], **options)
    run(
        f"{label} locked dependency security audit",
        [python, "-m", "pip_audit", "--strict", "--no-deps", "-r", "requirements.lock"],
        **options,
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
        ], **options,
    )


def package_gate(python311: str, python312: str, version: str = "0.4.1") -> None:
    dist = STAGE / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    for artifact in (*dist.glob("finrisk_agent-*.whl"), *dist.glob("finrisk_agent-*.tar.gz")):
        artifact.unlink()
    run("build wheel and sdist", [python311, "-m", "build", "--outdir", str(dist)])
    wheels = list(dist.glob(f"finrisk_agent-{version}-*.whl"))
    archives = list(dist.glob(f"finrisk_agent-{version}.tar.gz"))
    if len(wheels) != 1 or len(archives) != 1:
        raise SystemExit(f"package build did not produce exactly one v{version} wheel and sdist")
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


def research_and_docs_gate(python: str, module: str = "scripts.verify_v041") -> None:
    run("checked-in artifact gate", [python, "-m", module, "--ci"])
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


def container_gate(
    docker: str, python: str, version: str = "0.4.1",
    build_options: list[str] | None = None,
) -> None:
    common = {
        **os.environ,
        "FINRISK_LLM_PROVIDER": "mock",
        "NO_PROXY": "localhost,127.0.0.1,::1",
        "no_proxy": "localhost,127.0.0.1,::1",
        "PYTHONPATH": "backend",
    }
    development = ["docker-compose.yml", "docker-compose.prod.yml", "docker-compose.candidate.yml"]
    release = ["docker-compose.release.yml"]
    dev_env = {
        **common,
        "POSTGRES_PASSWORD": "local-gate-development-password",
        "FINRISK_BOOTSTRAP_TOKEN": "local-gate-development-bootstrap",
        "CANDIDATE_API_IMAGE": f"finrisk-v{version}-gate-api:candidate",
        "CANDIDATE_WEB_IMAGE": f"finrisk-v{version}-gate-web:candidate",
    }
    release_env = {
        **common,
        "POSTGRES_PASSWORD": "local-gate-release-password",
        "FINRISK_BOOTSTRAP_TOKEN": "local-gate-release-bootstrap",
        "FINRISK_API_IMAGE": f"finrisk-v{version}-gate-api:candidate",
        "FINRISK_WEB_IMAGE": f"finrisk-v{version}-gate-web:candidate",
    }
    subprocess.run(compose(docker, release, "down", "-v"), cwd=ROOT, env=release_env, check=False)
    subprocess.run(compose(docker, development, "down", "-v"), cwd=ROOT, env=dev_env, check=False)
    try:
        run(
            "build release API candidate",
            [docker, "build", *(build_options or []), "-f", "backend/Dockerfile", "-t", release_env["FINRISK_API_IMAGE"], "."],
            env=release_env,
        )
        run(
            "build release web candidate",
            [docker, "build", *(build_options or []), "-f", "frontend/Dockerfile", "-t", release_env["FINRISK_WEB_IMAGE"], "frontend"],
            env=release_env,
        )
        # Local image IDs pin the exact built artifact. They are not registry
        # manifest digests and must never be reported as remote attestations.
        ids = {
            service: subprocess.check_output(
                [docker, "image", "inspect", release_env[f"FINRISK_{service.upper()}_IMAGE"],
                 "--format", "{{.Id}}"], text=True,
            ).strip()
            for service in ("api", "web")
        }
        for service, identity in ids.items():
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
                raise SystemExit(f"invalid local candidate image identity: {service}")
            dev_env[f"CANDIDATE_{service.upper()}_IMAGE"] = identity
            release_env[f"FINRISK_{service.upper()}_IMAGE"] = identity
        (STAGE / "candidate-image-ids.json").write_text(json.dumps(ids, sort_keys=True) + "\n")
        run("development Compose candidate start", compose(docker, development, "up", "--no-build", "-d", "postgres", "migrate", "api", "web"), env=dev_env)
        verify_container_identities(docker, development, dev_env, ids)
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
        verify_container_identities(docker, release, release_env, ids)
        wait_http("http://127.0.0.1:8000/health/ready")
        wait_http("http://127.0.0.1:8000/health/live")
        run("release container HTTP contracts", [python, "scripts/verify_docker_health.py"], env=release_env)
        postgres_env = {
            **release_env,
            "DATABASE_URL": "postgresql://finrisk:local-gate-release-password@127.0.0.1:55432/finrisk",
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
    except (Exception, SystemExit):
        # Retain startup/runtime diagnostics before the disposable containers are
        # removed. Collection must not replace the original gate failure.
        for files, env in ((development, dev_env), (release, release_env)):
            try:
                subprocess.run(
                    compose(docker, files, "logs", "--no-color", "postgres", "migrate", "api", "web"),
                    cwd=ROOT, env=env, check=False,
                )
            except OSError as exc:
                print(f"Could not collect container diagnostics: {type(exc).__name__}", flush=True)
        raise
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
