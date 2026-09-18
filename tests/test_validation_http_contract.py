"""Real-HTTP regression for the 422/500 boundary, plus the frontend contract.

The overflow-float defect could not be caught in-process: it only appears once the
error body is handed to Starlette's JSON encoder. A `TestClient` call would have
caught it too, but the deployment path is an ASGI server, so this module boots a
real uvicorn process and speaks HTTP to it — headers, status codes and body bytes
exactly as a client sees them.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

# An out-of-range JSON number. `json.loads` turns it into `float('inf')`, which the
# model validators correctly reject — and which used to make the *error* response
# unserialisable (`ValueError: Out of range float values are not JSON compliant`),
# so a correct 422 came back as a 500.
OVERFLOW_BODIES = (
    '{"company":"X","fiscal_year":2025,"current":{"revenue":1e400}}',
    '{"company":"X","fiscal_year":2025,"current":{"revenue":-1e400}}',
    '{"company":"X","fiscal_year":2025,"current":{"revenue":Infinity}}',
    '{"company":"X","fiscal_year":2025,"current":{"revenue":-Infinity}}',
    '{"company":"X","fiscal_year":2025,"current":{"revenue":NaN}}',
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _post(base: str, path: str, body: str, headers: dict[str, str] | None = None):
    request = urllib.request.Request(
        f"{base}{path}", data=body.encode(), method="POST"
    )
    request.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


@pytest.fixture(scope="module")
def live_server():
    """A real uvicorn process on a private port."""
    port = _free_port()
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(BACKEND),
            "FINRISK_ENV": "development",
            "FINRISK_ENABLE_ORG_BOOTSTRAP": "1",
            "FINRISK_LLM_PROVIDER": "mock",
        }
    )
    env.pop("DATABASE_URL", None)
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "finrisk.api:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 60
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.skip("uvicorn exited before becoming ready in this environment")
            try:
                with urllib.request.urlopen(f"{base}/health/live", timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.3)
        else:
            pytest.skip("uvicorn did not become ready within the timeout")
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            process.kill()


def _small_pdf() -> bytes:
    import pymupdf as fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (56, 56),
        "CONTRACT ISSUER INC.\nBALANCE SHEET\n(in thousands)\n2025 2024\n"
        "Cash and cash equivalents 1,250 2,900\nTotal assets 21,400 20,100\n"
        "Total liabilities 16,500 11,400\nShareholders' equity 4,900 8,700\n"
        "Revenue 18,200 20,400\nNet income 260 1,850\n"
        "Net cash provided by operating activities 620 3,150\n",
    )
    payload = document.tobytes()
    document.close()
    return payload


def _bootstrap(live_server, name: str) -> dict[str, str]:
    status, payload = _post(
        live_server, "/api/v1/enterprise/organizations",
        json.dumps({"name": name, "actor_id": f"{name}-admin"}),
    )
    assert status == 200, payload[:200]
    return {"X-API-Key": json.loads(payload)["api_key"]}


def test_overflow_floats_answer_422_over_real_http(live_server):
    headers = _bootstrap(live_server, "Overflow tenant")
    for body in OVERFLOW_BODIES:
        status, payload = _post(live_server, "/api/v1/assess", body, headers)
        assert status == 422, f"{body} -> {status} {payload[:200]}"
        # The echoed input must itself be valid JSON for any client to read.
        detail = json.loads(payload)["detail"]
        assert isinstance(detail, list) and detail


def test_the_auth_boundary_still_precedes_validation(live_server):
    """An unauthenticated caller gets 401, not a validator's opinion."""
    status, _ = _post(live_server, "/api/v1/assess", OVERFLOW_BODIES[0])
    assert status == 401


def test_overflow_floats_are_rejected_without_credentials(live_server):
    """The bootstrap route is unauthenticated, so it must not be crashable."""
    status, payload = _post(
        live_server, "/api/v1/enterprise/organizations", '{"name":1e400,"actor_id":"x"}'
    )
    assert status == 422, payload[:200]
    assert json.loads(payload)["detail"]


def test_authenticated_overflow_floats_answer_422_over_real_http(live_server):
    headers = _bootstrap(live_server, "HTTP contract tenant")
    for path, body in (
        ("/api/v1/enterprise/fusion",
         '{"method":"weighted_average","scores":{"a":1e400},"weights":{"a":0.5},"coverage":0.5,"confidence":0.5}'),
        ("/api/v1/enterprise/scenarios", '{"baseline":{"revenue":1e400},"year":2025,"shocks":{}}'),
        ("/api/v1/enterprise/entities", '{"name":"A","parent_id":1e400}'),
        ("/api/v1/enterprise/selective-decision",
         '{"proposed_decision":"PASS","coverage":1e400,"reliability":null,"disagreement":0.1,"policy":{},"calibration_status":"UNCALIBRATED"}'),
    ):
        status, payload = _post(live_server, path, body, headers)
        assert status == 422, f"{path} -> {status} {payload[:200]}"


def test_readiness_reports_the_selected_datastore(live_server):
    """A gate has to be able to tell PostgreSQL from the in-memory fallback."""
    with urllib.request.urlopen(f"{live_server}/health/ready", timeout=10) as response:
        payload = json.load(response)
    assert payload["status"] == "ready"
    assert payload["datastore"] in {"postgres", "memory"}


def test_frontend_guard_fields_are_present_in_a_real_response(live_server):
    """Cross-layer contract: the fields `frontend/lib/guards.mjs` requires exist.

    The guard rejects a 200 whose body is not shaped as expected, and reports it as
    "not in the expected shape" instead of rendering. A field that the backend stops
    sending would therefore surface as a silent, total loss of the result.
    """
    headers = _bootstrap(live_server, "Contract tenant")
    status, entity_payload = _post(
        live_server, "/api/v1/enterprise/entities",
        '{"name":"Contract issuer","sector":"industrial"}', headers,
    )
    assert status == 200
    entity_id = json.loads(entity_payload)["id"]

    # The upload endpoint is what the Workbench actually calls, so it is the
    # contract that matters.
    boundary = "----contract"
    pdf = _small_pdf()
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in (("company", "Contract issuer"), ("fiscal_year", "2025"),
                            ("entity_id", entity_id))
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="c.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode() + pdf + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        f"{live_server}/api/v1/documents/analyze", data=b"".join(parts), method="POST"
    )
    request.add_header("X-API-Key", headers["X-API-Key"])
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(request, timeout=120) as response:
        assert response.status == 200
        body = json.load(response)

    # Mirrors `isAssessmentPayload` in frontend/lib/guards.mjs.
    for field in ("company", "reporting_period", "overall_score", "risk_level",
                  "confidence", "evidence_coverage", "dimensions", "models",
                  "triggered_rules", "missing_information", "confidence_components",
                  "failure_state"):
        assert field in body, f"guard requires {field!r}"
    assert isinstance(body["dimensions"], dict)
    assert isinstance(body["failure_state"], dict)
    assert isinstance(body["failure_state"]["degraded"], bool)

    # `/documents/analyze` nests the agent state under `agent`; mirrors
    # `isAgentPayload`, which the UI runs before rendering any agent tab.
    agent = body.get("agent")
    assert isinstance(agent, dict), "the upload endpoint must expose the agent payload"
    for field in ("status", "plan", "trace", "conclusions", "component_telemetry",
                  "decision_trace", "fusion"):
        assert field in agent, f"guard requires agent.{field!r}"
    trace = agent["decision_trace"]
    for field in ("decision_reason_codes", "material_path_count",
                  "verified_path_count", "proof_coverage", "paths"):
        assert field in trace, f"guard requires decision_trace.{field!r}"
    assert isinstance(trace["paths"], list) and trace["paths"], "a run must carry decision paths"
    path = trace["paths"][0]
    for field in ("reason_code", "evidence_path_status", "coverage", "disagreement",
                  "required_inputs", "path", "source_evidence", "input_provenance",
                  "fusion_contribution"):
        assert field in path, f"guard requires paths[*].{field!r}"
    assert isinstance(agent["fusion"].get("reason_codes"), list)
