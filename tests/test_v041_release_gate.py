from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import verify_v041_release as gate


def test_compose_cleanup_is_scoped_to_disposable_project():
    command = gate.compose("docker", ["docker-compose.release.yml"], "down", "-v")
    assert command[:4] == ["docker", "compose", "--project-name", "finrisk-v041-release-gate"]
    assert command[4:] == ["-f", "docker-compose.release.yml", "down", "-v"]


def test_wrong_interpreter_cannot_claim_matrix_success(monkeypatch):
    monkeypatch.setattr(gate.subprocess, "check_output", lambda *_args, **_kw: "[3, 12]")
    monkeypatch.setattr(gate, "run", lambda *_args, **_kw: pytest.fail("wrong runtime must stop"))
    with pytest.raises(SystemExit, match="supplied interpreter"):
        gate.python_gate("python", "Python 3.11")


def test_backend_gate_preserves_coverage_and_security_audit(monkeypatch):
    commands = []
    monkeypatch.setattr(gate.subprocess, "check_output", lambda *_args, **_kw: "[3, 12]")
    monkeypatch.setattr(gate, "run", lambda label, command: commands.append(command))
    gate.python_gate("python", "Python 3.12")
    assert commands[0] == ["python", "-m", "pip", "check"]
    assert commands[1] == ["python", "-m", "pip_audit", "--strict", "--no-deps", "-r", "requirements.lock"]
    assert "--cov-fail-under=90" in commands[2]
    assert any(arg.startswith("--junitxml=") for arg in commands[2])
    assert any(arg.startswith("--cov-report=json:") for arg in commands[2])


def test_frontend_gate_audits_production_dependencies(monkeypatch):
    commands = []
    monkeypatch.setattr(gate, "run", lambda label, command: commands.append(command))
    gate.frontend_gate("npm")
    assert commands[1] == ["npm", "--prefix", "frontend", "audit", "--omit=dev", "--audit-level=high"]
    assert [command[-1] for command in commands[2:]] == ["test", "lint", "typecheck", "build"]


def test_package_smoke_can_run_outside_checkout(monkeypatch, tmp_path):
    seen = {}

    def execute(command, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(gate.subprocess, "run", execute)
    gate.run("isolated smoke", ["python", "smoke.py"], cwd=tmp_path, env={"PYTHONPATH": ""})
    assert seen["cwd"] == tmp_path
    assert seen["env"]["PYTHONPATH"] == ""
