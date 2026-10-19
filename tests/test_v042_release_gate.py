from __future__ import annotations

from types import SimpleNamespace

import pytest
import yaml

from scripts import verify_v041_release as gate
from scripts.verify_v041_release import ROOT
from scripts.verify_v042 import verify_release_metadata


@pytest.mark.parametrize("event,ref,publish,verified,expected", [
    ("workflow_dispatch", "refs/heads/try-v0.4.2", False, True, False),
    ("workflow_dispatch", "refs/tags/v0.4.2", False, True, False),
    ("workflow_dispatch", "refs/heads/try-v0.4.2", True, True, True),
    ("workflow_dispatch", "refs/tags/v0.4.2", True, True, True),
    ("push", "refs/tags/v0.4.2", False, True, True),
    ("push", "refs/heads/try-v0.4.2", False, True, False),
    ("push", "refs/tags/v0.4.2", False, False, False),
    ("workflow_dispatch", "refs/heads/try-v0.4.2", True, False, False),
])
def test_actual_workflow_dry_run_never_publishes_and_failed_gates_block(event, ref, publish, verified, expected):
    workflow = yaml.safe_load((ROOT / ".github/workflows/container-release.yml").read_text())
    expression = workflow["jobs"]["publish"]["if"]
    expression = expression.replace("&&", " and ").replace("||", " or ")
    expression = expression.replace("needs.verify-release-compose", "needs.release_compose")
    state = SimpleNamespace(result="success" if verified else "failure")
    context = {
        "needs": SimpleNamespace(verify=state, release_compose=state, scan=state),
        "github": SimpleNamespace(event_name=event, ref=ref),
        "inputs": SimpleNamespace(publish=publish), "true": True,
        "startsWith": str.startswith,
    }
    # Evaluate only the repository's trusted, checked-in expression. This is a
    # regression harness, not a decoder for external GitHub/user input.
    assert eval(expression.strip(), {"__builtins__": {}}, context) is expected


@pytest.mark.parametrize("changelog", ["", "## [0.4.1] - historical\n## [0.4.2] - current", "## Unreleased"])
def test_current_release_cannot_use_missing_or_stale_changelog(tmp_path, changelog):
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    with pytest.raises(SystemExit, match="newest changelog release"):
        verify_release_metadata(tmp_path)


def test_current_release_requires_current_documentation(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("## [0.4.2] - 2026-10-08")
    (tmp_path / "RELEASE_NOTES_v0.4.2.md").write_text("v0.4.1")
    with pytest.raises(SystemExit, match="documentation drift"):
        verify_release_metadata(tmp_path)


@pytest.mark.parametrize("service", ["api", "web", "migrate"])
def test_local_gate_rejects_substituted_candidate_image(monkeypatch, service):
    def output(command, **_):
        if command[1] == "compose":
            return command[-1]
        return "substituted" if command[-1] == service else "expected"

    monkeypatch.setattr(gate.subprocess, "check_output", output)
    with pytest.raises(SystemExit, match="verified candidate artifact"):
        gate.verify_container_identities("docker", [], {}, {"api": "expected", "web": "expected"})


def test_local_gate_preserves_failure_diagnostics_before_cleanup(monkeypatch):
    commands = []
    monkeypatch.setattr(gate.subprocess, "run", lambda command, **_: commands.append(command))
    monkeypatch.setattr(gate.subprocess, "check_output", lambda *_, **__: "a" * 40)

    def fail(*_, **__):
        raise SystemExit("candidate build failed")

    monkeypatch.setattr(gate, "run", fail)
    with pytest.raises(SystemExit, match="candidate build failed"):
        gate.container_gate("docker", "python", "0.4.2")
    diagnostic_indexes = [i for i, command in enumerate(commands) if "logs" in command]
    assert len(diagnostic_indexes) == 2
    assert all("postgres" in commands[i] and "api" in commands[i] for i in diagnostic_indexes)
    cleanup_indexes = [i for i, command in enumerate(commands) if "down" in command]
    assert max(diagnostic_indexes) < min(cleanup_indexes[-2:])


def test_opt_in_cache_reclamation_preserves_candidates_and_build_order(monkeypatch):
    commands = []
    monkeypatch.setattr(gate.subprocess, 'run', lambda *_, **__: None)
    monkeypatch.setattr(gate.subprocess, 'check_output', lambda *_, **__: 'sha256:' + 'a'*64)

    def record(label, command, **_):
        commands.append(command)
        if 'scripts/verify_candidate_image.py' in command:
            raise SystemExit('stop after successful builds')

    monkeypatch.setattr(gate, 'run', record)
    with pytest.raises(SystemExit, match='stop after successful builds'):
        gate.container_gate('docker', 'python', '0.4.2', prune_build_cache=True)
    builds = [i for i,c in enumerate(commands) if c[:2] == ['docker', 'build']]
    prunes = [i for i,c in enumerate(commands) if c == ['docker', 'builder', 'prune', '--all', '--force']]
    assert len(builds) == len(prunes) == 2
    assert builds[0] < prunes[0] < builds[1] < prunes[1]
    assert not any(c[:3] in (['docker', 'image', 'rm'], ['docker', 'system', 'prune']) for c in commands)
