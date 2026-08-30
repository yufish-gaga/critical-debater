"""Debate run management: background graph execution + live event feed (v3 Phase 6).

The service runs the LangGraph debate in a daemon thread per debate and
tracks run state. The WebSocket endpoint tails two cheap, mtime-guarded
sources for live progress — the workspace ``config.json`` status and the
JSONL audit trail — and pushes events as they appear.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional

from ..config import DebateOptions
from ..errors import DebateStepFailure
from ..graph.runner import run_debate
from ..workspace import audit_file, config_path, init_workspace

# Artifacts the UI can fetch; mapped to workspace-relative paths.
ARTIFACT_PATHS: dict[str, str] = {
    "config": "config.json",
    "evidence_store": os.path.join("evidence", "evidence_store.json"),
    "evidence_credibility": os.path.join("evidence", "evidence_credibility.json"),
    "evidence_graph": os.path.join("evidence", "evidence_graph.json"),
    "claim_ledger": os.path.join("claims", "claim_ledger.json"),
    "quality_metrics": os.path.join("reports", "quality_metrics.json"),
    "final_report": os.path.join("reports", "final_report.json"),
}

TERMINAL_STATUSES = {
    "complete", "failed_initialization", "failed_final_synthesis", "failed_report_validation",
}
TERMINAL_PREFIX = "failed_round_"


def artifact_path(workspace: str, name: str) -> Optional[str]:
    relative = ARTIFACT_PATHS.get(name)
    return os.path.join(workspace, relative) if relative else None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _terminal(config_status: str) -> bool:
    return config_status in TERMINAL_STATUSES or config_status.startswith(TERMINAL_PREFIX)


@dataclass
class DebateRun:
    """State of one debate run managed by the service."""

    debate_id: str
    workspace: str
    topic: str
    rounds: int
    status: str = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = None
    version: int = 0  # bumped on every state change; lets WS clients detect updates


class DebateService:
    """Runs debates in background threads and exposes their live state."""

    def __init__(self, runner_factory: Optional[Callable[[], Any]] = None, runs_root: str = "/tmp"):
        self._runs: dict[str, DebateRun] = {}
        self._lock = threading.Lock()
        self._runner_factory = runner_factory  # None → default get_runner()
        self._runs_root = runs_root

    # -- lifecycle -----------------------------------------------------------

    def start(self, request) -> DebateRun:
        workspace = request.workspace or os.path.join(
            self._runs_root, "debate-" + uuid.uuid4().hex[:8]
        )
        workspace = os.path.abspath(workspace)
        if not os.path.exists(config_path(workspace)):
            init_workspace(
                workspace, request.topic, request.rounds,
                depth=request.depth, mode=request.mode, language=request.language,
            )

        opts = DebateOptions(
            topic=request.topic,
            rounds=request.rounds,
            depth=request.depth,
            mode=request.mode,
            language=request.language,
        )
        run = DebateRun(
            debate_id=uuid.uuid4().hex[:12],
            workspace=workspace,
            topic=request.topic,
            rounds=request.rounds,
            status="running",
            started_at=_now(),
        )
        run.thread = threading.Thread(
            target=self._execute, args=(run, opts), name=f"debate-{run.debate_id}", daemon=True,
        )
        with self._lock:
            self._runs[run.debate_id] = run
        run.thread.start()
        return run

    def _execute(self, run: DebateRun, opts: DebateOptions) -> None:
        from ..models.registry import get_runner

        try:
            runner = self._runner_factory() if self._runner_factory else get_runner()
            final_state = run_debate(run.workspace, opts, runner=runner)
            run.status = str(final_state.get("status", "complete"))
        except DebateStepFailure as e:
            run.status = e.status
            run.error = str(e)
        except Exception as e:  # pragma: no cover — defensive for the thread
            run.status = "failed_unexpected"
            run.error = f"{type(e).__name__}: {e}"
        finally:
            run.finished_at = _now()
            run.version += 1

    def _config_status(self, workspace: str) -> Optional[str]:
        try:
            with open(config_path(workspace), encoding="utf-8") as f:
                return json.load(f).get("status")
        except (OSError, json.JSONDecodeError):
            return None

    # -- accessors -------------------------------------------------------------

    def get(self, debate_id: str) -> Optional[DebateRun]:
        return self._runs.get(debate_id)

    def list(self) -> list[DebateRun]:
        return list(self._runs.values())

    def sync_status(self, run: DebateRun) -> None:
        """Refresh run.status from workspace config (the graph writes it directly)."""
        cfg_status = self._config_status(run.workspace)
        if cfg_status and cfg_status != run.status and not _terminal(run.status):
            run.status = cfg_status
            run.version += 1

    # -- live feed (async, mtime-guarded polling) --------------------------------

    def snapshot(self, run: DebateRun) -> dict:
        self.sync_status(run)
        return {
            "type": "snapshot",
            "debate_id": run.debate_id,
            "status": run.status,
            "topic": run.topic,
            "rounds": run.rounds,
            "error": run.error,
            "audit": self.read_audit(run.workspace),
        }

    @staticmethod
    def read_audit(workspace: str, tail: int = 100) -> list[dict]:
        path = audit_file(workspace)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        entries = []
        for line in lines[-tail:]:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    async def event_stream(self, run: DebateRun, stop: Callable[[], bool],
                           poll_sec: float = 0.5) -> AsyncIterator[tuple[str, dict | str]]:
        """Yield ('audit', entry) and ('status', status) events as files change."""
        audit_path = audit_file(run.workspace)
        config_p = config_path(run.workspace)
        audit_offset = 0
        last_audit_mtime = 0.0
        last_status: Optional[str] = None

        while not stop():
            try:
                if os.path.exists(audit_path):
                    mtime = os.path.getmtime(audit_path)
                    if mtime != last_audit_mtime:
                        size = os.path.getsize(audit_path)
                        if size < audit_offset:  # truncated/rewritten
                            audit_offset = 0
                        with open(audit_path, encoding="utf-8") as f:
                            f.seek(audit_offset)
                            new_lines = f.readlines()
                            audit_offset = f.tell()
                        last_audit_mtime = mtime
                        for line in new_lines:
                            line = line.strip()
                            if line:
                                try:
                                    yield "audit", json.loads(line)
                                except json.JSONDecodeError:
                                    continue

                if os.path.exists(config_p):
                    try:
                        with open(config_p, encoding="utf-8") as f:
                            status = json.load(f).get("status")
                    except (OSError, json.JSONDecodeError):
                        status = None
                    if status and status != last_status:
                        last_status = status
                        yield "status", status

                # Thread-level terminal state (e.g. failed_unexpected) that
                # never landed in config.json still ends the stream.
                if _terminal(run.status):
                    yield "status", run.status
                    return
            except OSError:
                pass
            await asyncio.sleep(poll_sec)
