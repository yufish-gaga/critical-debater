"""Tests for the API security boundary (v3.1 安全边界)."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from critical_debater.api.app import create_app
from critical_debater.api.service import DebateService
from critical_debater.workspace import config_path, read_json

from conftest import REPORT_MD_FIXTURE
from fake_agent import FakeScriptedRunner


def make_service(tmp_path, **kwargs):
    return DebateService(
        runner_factory=lambda: FakeScriptedRunner(
            initial_evidence=10, report_md_fixture=REPORT_MD_FIXTURE),
        runs_root=str(tmp_path / "runs"),
        **kwargs,
    )


# --- token auth ----------------------------------------------------------------


def test_http_requires_token_when_configured(tmp_path):
    client = TestClient(create_app(service=make_service(tmp_path), frontend_dist=None,
                                    api_token="s3cret"))
    assert client.get("/api/debates").status_code == 401
    assert client.get("/api/debates", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.get("/api/debates", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    # Alternative header form.
    ok2 = client.get("/api/debates", headers={"X-Api-Token": "s3cret"})
    assert ok2.status_code == 200
    # POST protected too.
    assert client.post("/api/debates", json={"topic": "t"}).status_code == 401


def test_ws_rejects_missing_or_wrong_token(tmp_path):
    client = TestClient(create_app(service=make_service(tmp_path), frontend_dist=None,
                                    api_token="s3cret"))
    start = client.post("/api/debates", json={"topic": "t"},
                        headers={"Authorization": "Bearer s3cret"}).json()

    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(f"/ws/{start['debate_id']}") as ws:
            ws.receive_json()  # server accepts, then closes with 4401
    assert excinfo.value.code == 4401

    # Wrong token also rejected.
    with pytest.raises(WebSocketDisconnect) as excinfo2:
        with client.websocket_connect(f"/ws/{start['debate_id']}?token=nope") as ws:
            ws.receive_json()
    assert excinfo2.value.code == 4401

    # Correct token (query param form — browsers cannot set WS headers).
    with client.websocket_connect(f"/ws/{start['debate_id']}?token=s3cret") as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot"


def test_token_disabled_by_default(tmp_path):
    client = TestClient(create_app(service=make_service(tmp_path), frontend_dist=None))
    assert client.get("/api/debates").status_code == 200
    # Env fallback: unset here, so open.
    import os

    assert os.environ.get("CRITICAL_DEBATER_API_TOKEN") in (None, "")


# --- workspace confinement -------------------------------------------------------


def test_workspace_outside_root_rejected(tmp_path):
    client = TestClient(create_app(service=make_service(tmp_path), frontend_dist=None))
    # workspace_root = <tmp_path>/runs (derived from runs_root).

    outside = client.post("/api/debates", json={
        "topic": "t", "workspace": str(tmp_path / "elsewhere" / "ws")})
    assert outside.status_code == 403
    assert "outside the allowed root" in outside.json()["detail"]

    # Inside the root is accepted.
    inside = client.post("/api/debates", json={
        "topic": "t", "workspace": str(tmp_path / "runs" / "ws")})
    assert inside.status_code == 200

    # Traversal attempt resolves to outside → 403.
    sneaky = client.post("/api/debates", json={
        "topic": "t", "workspace": str(tmp_path / "runs" / ".." / ".." / "escape")})
    assert sneaky.status_code == 403


# --- cancellation ------------------------------------------------------------------


class BlockingRunner:
    """Blocks on the first dispatched step until released (deterministic cancel)."""

    runtime = "blocking"

    def __init__(self, release: threading.Event):
        self.release = release

    def run(self, step_id: str, prompt: str, model_tier: str = "balanced",
            timeout_sec: int = 300, context=None):
        self.release.wait(timeout=10)
        from critical_debater.models.base import StepResult

        return StepResult(step_id=step_id, success=False,
                          error_type="blocked", reason="released")


def test_cancel_running_debate(tmp_path):
    release = threading.Event()
    service = DebateService(runner_factory=lambda: BlockingRunner(release),
                            runs_root=str(tmp_path / "runs"))
    client = TestClient(create_app(service=service, frontend_dist=None))
    debate_id = client.post("/api/debates", json={"topic": "t"}).json()["debate_id"]

    # Wait until the run is actually blocked inside the first step.
    deadline = time.time() + 10
    while time.time() < deadline:
        run = service.get(debate_id)
        if run and run.thread and run.thread._started.is_set() and not run.thread.is_alive() is False:
            pass
        time.sleep(0.1)
        break

    resp = client.post(f"/api/debates/{debate_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["cancelled"] is True

    release.set()  # let the blocked step return → wrapper observes the cancel

    deadline = time.time() + 10
    while time.time() < deadline:
        status = client.get(f"/api/debates/{debate_id}").json()["status"]
        if status == "cancelled":
            break
        time.sleep(0.2)
    assert status == "cancelled"
    assert read_json(config_path(service.get(debate_id).workspace))["status"] == "cancelled"

    # Cancelling again is a no-op (already terminal).
    second = client.post(f"/api/debates/{debate_id}/cancel").json()
    assert second["cancelled"] is False


def test_cancel_unknown_debate_404(tmp_path):
    client = TestClient(create_app(service=make_service(tmp_path), frontend_dist=None))
    assert client.post("/api/debates/nope/cancel").status_code == 404


# --- resume via API ------------------------------------------------------------------


def test_start_with_resume_continues_checkpoint(tmp_path):
    service = make_service(tmp_path)
    client = TestClient(create_app(service=service, frontend_dist=None))

    # Stage a final-synthesis failure in a dedicated runner.
    from fake_agent import FakeScriptedRunner

    service._runner_factory = lambda: FakeScriptedRunner(
        initial_evidence=10, final_synthesis_ok=False, final_synthesis_writes_json=False)
    first = client.post("/api/debates", json={"topic": "t", "rounds": 1}).json()
    workspace = first["workspace"]
    deadline = time.time() + 20
    while time.time() < deadline:
        if client.get(f"/api/debates/{first['debate_id']}").json()["status"] == "failed_final_synthesis":
            break
        time.sleep(0.2)

    # Resume with a healthy runner → completes without redoing rounds.
    service._runner_factory = lambda: FakeScriptedRunner(
        initial_evidence=10, report_md_fixture=REPORT_MD_FIXTURE)
    second = client.post("/api/debates", json={
        "topic": "t", "rounds": 1, "workspace": workspace, "resume": True})
    assert second.status_code == 200
    second_id = second.json()["debate_id"]

    deadline = time.time() + 30
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/debates/{second_id}").json()["status"]
        if status == "complete" or status.startswith("failed_"):
            break
        time.sleep(0.2)
    assert status == "complete"


def test_resume_without_checkpoint_404(tmp_path):
    client = TestClient(create_app(service=make_service(tmp_path), frontend_dist=None))
    missing = tmp_path / "runs" / "ghost"
    missing.mkdir(parents=True)
    resp = client.post("/api/debates", json={
        "topic": "t", "workspace": str(missing), "resume": True})
    assert resp.status_code == 404
