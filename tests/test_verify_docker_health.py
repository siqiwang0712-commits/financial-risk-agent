from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from finrisk import verification_http
from finrisk.verification_http import assert_readiness, wait_for_json_object

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_docker_health.py"


def load_script():
    spec = importlib.util.spec_from_file_location("verify_docker_health_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_named_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_readiness_requires_postgres_and_complete_schema():
    assert_readiness({"status": "ready", "datastore": "postgres", "schema": "complete"})

    with pytest.raises(RuntimeError, match="datastore"):
        assert_readiness({"status": "ready", "datastore": "memory", "schema": "complete"})

    with pytest.raises(RuntimeError, match="schema"):
        assert_readiness({"status": "ready", "datastore": "postgres", "schema": "pending"})


def test_json_endpoint_wait_retries_transport_and_contract_failures(monkeypatch):
    attempts = iter(
        [
            OSError("not listening yet"),
            {"runtime": "wrong"},
            {"runtime": "v0.3.3"},
        ]
    )

    def request(*_args, **_kwargs):
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    def validate(payload):
        if payload.get("runtime") != "v0.3.3":
            raise RuntimeError("wrong runtime")

    monkeypatch.setattr(verification_http, "request_json", request)
    monkeypatch.setattr(verification_http.time, "sleep", lambda _seconds: None)

    assert wait_for_json_object(
        "http://127.0.0.1:3000/api/v1/public-pilot",
        timeout=1,
        label="frontend proxy",
        validator=validate,
    )["runtime"] == "v0.3.3"


def test_verification_endpoints_and_runtime_are_configurable(monkeypatch):
    monkeypatch.setenv("FINRISK_VERIFY_API", "http://127.0.0.1:38000/")
    monkeypatch.setenv("FINRISK_VERIFY_WEB", "http://127.0.0.1:33000/")
    monkeypatch.setenv("FINRISK_EXPECTED_RUNTIME", "v9.9.9")

    verifier = load_script()

    assert verifier.API == "http://127.0.0.1:38000"
    assert verifier.WEB == "http://127.0.0.1:33000"
    assert verifier.EXPECTED_RUNTIME == "v9.9.9"


@pytest.mark.parametrize(
    "base",
    [
        "https://example.com:443",
        "http://user:secret@127.0.0.1:8000",
        "http://127.0.0.1:8000/prefix",
        "file:///tmp/api",
    ],
)
def test_verification_endpoints_are_loopback_origins(monkeypatch, base):
    monkeypatch.setenv("FINRISK_VERIFY_API", base)
    with pytest.raises(ValueError, match="loopback HTTP"):
        load_script()


def test_default_runtime_comes_from_project_metadata(monkeypatch):
    monkeypatch.delenv("FINRISK_EXPECTED_RUNTIME", raising=False)
    verifier = load_script()
    assert verifier.EXPECTED_RUNTIME == "v0.3.3"


@pytest.mark.parametrize(
    "script",
    ["verify_postgres_state.py", "verify_docker_timeout.py"],
)
def test_all_credentialed_verifiers_reject_remote_origins(monkeypatch, script):
    monkeypatch.setenv("FINRISK_VERIFY_API", "https://attacker.example:443")
    with pytest.raises(ValueError, match="loopback HTTP"):
        load_named_script(script)


def test_postgres_verifier_requires_complete_schema():
    verifier = load_named_script("verify_postgres_state.py")
    verifier.assert_postgres(
        {"status": "ready", "datastore": "postgres", "schema": "complete"}
    )
    with pytest.raises(SystemExit, match="complete schema"):
        verifier.assert_postgres(
            {"status": "ready", "datastore": "postgres", "schema": "pending"}
        )
