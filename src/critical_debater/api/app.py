"""FastAPI application (v3 Phase 6).

``create_app(service=None, frontend_dist=None)`` builds the app:

- REST: start debates, read status and workspace artifacts
- ``WS /ws/{debate_id}``: live snapshot + audit/status event stream
- optional static mount of the built React frontend (``frontend/dist``)
"""

from __future__ import annotations

import hmac
import json
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .schemas import (
    ArtifactResponse,
    DebateCancelResponse,
    DebateStartRequest,
    DebateStartResponse,
    DebateStatus,
)
from .service import DebateRun, DebateService, WorkspaceOutsideRoot, _terminal, artifact_path

DEFAULT_FRONTEND_DIST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "frontend", "dist",
)


def _read_config(service: DebateService, run: DebateRun) -> dict:
    try:
        with open(os.path.join(run.workspace, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _run_status_payload(service: DebateService, run: DebateRun) -> DebateStatus:
    service.sync_status(run)
    config = _read_config(service, run)
    return DebateStatus(
        debate_id=run.debate_id,
        workspace=run.workspace,
        topic=run.topic,
        rounds=run.rounds,
        current_round=int(config.get("current_round") or 0),
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
    )


def _extract_token(headers, query_params: Optional[dict] = None) -> str:
    auth = headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header_token = headers.get("x-api-token") or ""
    if header_token:
        return header_token.strip()
    if query_params:
        return str(query_params.get("token") or "").strip()
    return ""


def _token_valid(presented: str, expected: str) -> bool:
    return bool(presented) and hmac.compare_digest(presented, expected)


def create_app(service: Optional[DebateService] = None,
               frontend_dist: Optional[str] = None,
               api_token: Optional[str] = None) -> FastAPI:
    """Build the app.

    ``api_token``: when set (or env ``CRITICAL_DEBATER_API_TOKEN`` is present),
    every ``/api/*`` request and ``/ws/*`` connection must present the token
    via ``Authorization: Bearer …``, ``X-Api-Token: …`` or (WebSocket only)
    the ``?token=`` query parameter. The SPA shell itself stays public.
    """
    service = service if service is not None else DebateService()
    frontend_dist = frontend_dist if frontend_dist is not None else DEFAULT_FRONTEND_DIST
    if api_token is None:
        api_token = os.environ.get("CRITICAL_DEBATER_API_TOKEN", "")

    app = FastAPI(title="Critical Debater v3", version="3.0.0.phase6")
    app.state.service = service
    app.state.api_token = api_token

    @app.middleware("http")
    async def token_auth_middleware(request: Request, call_next):
        if api_token and request.url.path.startswith("/api/"):
            presented = _extract_token(request.headers)
            if not _token_valid(presented, api_token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "missing or invalid API token"},
                )
        return await call_next(request)

    # -- REST ---------------------------------------------------------------

    @app.post("/api/debates", response_model=DebateStartResponse)
    def start_debate(request: DebateStartRequest) -> DebateStartResponse:
        try:
            run = service.start(request)
        except WorkspaceOutsideRoot as e:
            raise HTTPException(status_code=403, detail=str(e))
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return DebateStartResponse(debate_id=run.debate_id, workspace=run.workspace, status=run.status)

    @app.get("/api/debates", response_model=list[DebateStatus])
    def list_debates() -> list[DebateStatus]:
        return [_run_status_payload(service, run) for run in service.list()]

    @app.get("/api/debates/{debate_id}", response_model=DebateStatus)
    def debate_status(debate_id: str) -> DebateStatus:
        run = service.get(debate_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown debate")
        return _run_status_payload(service, run)

    @app.post("/api/debates/{debate_id}/cancel", response_model=DebateCancelResponse)
    def cancel_debate(debate_id: str) -> DebateCancelResponse:
        try:
            run, was_running = service.cancel(debate_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown debate")
        return DebateCancelResponse(debate_id=debate_id, status=run.status, cancelled=was_running)

    @app.get("/api/debates/{debate_id}/artifacts/{name}", response_model=ArtifactResponse)
    def debate_artifact(debate_id: str, name: str) -> ArtifactResponse:
        run = service.get(debate_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown debate")
        path = artifact_path(run.workspace, name)
        if path is None:
            # Round artifacts: round_<n>_(pro_turn|con_turn|judge_ruling)
            import re

            match = re.fullmatch(r"round_(\d+)_(pro_turn|con_turn|judge_ruling)", name)
            if match:
                path = os.path.join(
                    run.workspace, "rounds", f"round_{match.group(1)}", f"{match.group(2)}.json"
                )
        if path is None:
            raise HTTPException(status_code=404, detail=f"unknown artifact: {name}")
        if not os.path.exists(path):
            return ArtifactResponse(debate_id=debate_id, name=name, exists=False)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=503, detail=f"artifact not valid JSON yet: {e}")
        return ArtifactResponse(debate_id=debate_id, name=name, exists=True, data=data)

    @app.get("/api/debates/{debate_id}/report")
    def debate_report(debate_id: str) -> dict:
        run = service.get(debate_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown debate")
        path = os.path.join(run.workspace, "reports", "debate_report.md")
        if not os.path.exists(path):
            return {"exists": False, "content": None}
        with open(path, encoding="utf-8") as f:
            return {"exists": True, "content": f.read()}

    # -- WebSocket ------------------------------------------------------------

    @app.websocket("/ws/{debate_id}")
    async def debate_ws(websocket: WebSocket, debate_id: str) -> None:
        if api_token and not _token_valid(
            _extract_token(websocket.headers, dict(websocket.query_params.multi_items())),
            api_token,
        ):
            await websocket.accept()
            await websocket.close(code=4401, reason="missing or invalid API token")
            return
        run = service.get(debate_id)
        if run is None:
            await websocket.close(code=4404)
            return
        await websocket.accept()
        await websocket.send_json(service.snapshot(run))
        stop = False
        try:
            async for kind, payload in service.event_stream(run, lambda: stop):
                event: dict = {"type": kind}
                if kind == "audit":
                    event["entry"] = payload
                else:
                    event["status"] = payload
                await websocket.send_json(event)
                if kind == "status" and _terminal(str(payload)):
                    stop = True
        except WebSocketDisconnect:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    # -- static frontend (built React app) --------------------------------------

    if frontend_dist and os.path.exists(os.path.join(frontend_dist, "index.html")):
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):  # noqa: ANN202
            candidate = os.path.join(frontend_dist, full_path)
            if full_path and os.path.isfile(candidate):
                return FileResponse(candidate)
            return FileResponse(os.path.join(frontend_dist, "index.html"))

    return app
