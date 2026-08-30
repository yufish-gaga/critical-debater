"""Phase 7 integration tests: full-stack e2e over the HTTP + WebSocket surface.

Exercises the FastAPI app end to end with the scripted fake runner:
start a debate → poll status → receive WS events → fetch artifacts →
read the report; plus the SPA static mount when a frontend build exists.
"""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from critical_debater.api.app import create_app
from critical_debater.api.service import DebateService

from conftest import REPORT_MD_FIXTURE
from fake_agent import FakeScriptedRunner

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")


@pytest.fixture()
def client(tmp_path):
    service = DebateService(
        runner_factory=lambda: FakeScriptedRunner(
            initial_evidence=10, report_md_fixture=REPORT_MD_FIXTURE
        ),
        runs_root=str(tmp_path),
    )
    app = create_app(service=service, frontend_dist=None)
    return TestClient(app), service


def _await_terminal(client: TestClient, debate_id: str, timeout: float = 30.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/api/debates/{debate_id}").json()["status"]
        if status == "complete" or status.startswith("failed_"):
            return status
        time.sleep(0.2)
    raise TimeoutError("debate did not finish in time")


def test_full_debate_over_http(client):
    http, _ = client
    # 1. start
    resp = http.post("/api/debates", json={"topic": "Integration topic", "rounds": 2})
    assert resp.status_code == 200
    body = resp.json()
    debate_id = body["debate_id"]
    assert body["status"] == "running"

    # 2. status transitions to terminal
    status = _await_terminal(http, debate_id)
    assert status == "complete"

    # 3. status payload carries workspace progress
    status_payload = http.get(f"/api/debates/{debate_id}").json()
    assert status_payload["rounds"] == 2
    assert status_payload["current_round"] == 2
    assert status_payload["workspace"]

    # 4. artifacts
    evidence = http.get(f"/api/debates/{debate_id}/artifacts/evidence_store").json()
    assert evidence["exists"] and len(evidence["data"]) == 14  # 10 + 4 turn discoveries

    quality = http.get(f"/api/debates/{debate_id}/artifacts/quality_metrics").json()
    assert quality["exists"]
    dims = [d["dimension"] for d in quality["data"]["dimensions"]]
    assert len(dims) == 8  # Phase 5 eight-dimension report
    assert 0.0 <= quality["data"]["overall_score"] <= 1.0

    round_turn = http.get(f"/api/debates/{debate_id}/artifacts/round_1_pro_turn").json()
    assert round_turn["exists"] and round_turn["data"]["side"] == "pro"

    ruling = http.get(f"/api/debates/{debate_id}/artifacts/round_2_judge_ruling").json()
    assert ruling["exists"] and ruling["data"]["round"] == 2

    # 5. report
    report = http.get(f"/api/debates/{debate_id}/report").json()
    assert report["exists"]
    assert "# Debate Report:" in report["content"]

    # 6. unknowns
    assert http.get("/api/debates/does-not-exist").status_code == 404
    assert http.get(f"/api/debates/{debate_id}/artifacts/nope").status_code == 404


def test_websocket_event_stream(client):
    http, _ = client
    resp = http.post("/api/debates", json={"topic": "WS topic", "rounds": 1})
    debate_id = resp.json()["debate_id"]

    terminal_seen = False
    audit_seen = False
    with http.websocket_connect(f"/ws/{debate_id}") as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["debate_id"] == debate_id
        # Any live status is acceptable: the run may already be mid-flight.
        assert isinstance(snapshot["status"], str) and snapshot["status"]

        for _ in range(300):
            msg = ws.receive_json()
            if msg["type"] == "audit":
                audit_seen = True
            elif msg["type"] == "status":
                if msg["status"] == "complete" or msg["status"].startswith("failed_"):
                    terminal_seen = True
                    break
        assert terminal_seen, "WS stream must end with a terminal status event"
    assert audit_seen, "WS stream must carry audit trail events"


def test_start_reuses_existing_workspace(client, workspace):
    http, _ = client
    resp = http.post(
        "/api/debates",
        json={"topic": "Test topic", "rounds": 1, "workspace": workspace},
    )
    assert resp.status_code == 200
    assert resp.json()["workspace"] == os.path.abspath(workspace)


def test_static_frontend_mount_when_built():
    if not os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        pytest.skip("frontend not built (frontend/dist missing)")
    service = DebateService(runner_factory=lambda: FakeScriptedRunner(), runs_root="/tmp")
    client = TestClient(create_app(service=service, frontend_dist=FRONTEND_DIST))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Critical Debater" in resp.text and "辩论系统" in resp.text
    # SPA fallback: unknown client-side routes serve the app shell too.
    assert client.get("/some/client/route").status_code == 200
