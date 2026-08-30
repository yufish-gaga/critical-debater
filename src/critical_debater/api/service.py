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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional

from ..config import DebateOptions
from ..errors import DebateStepFailure
from ..graph.runner import run_debate
from ..workspace import audit_file, config_path, init_workspace, update_config

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
    "complete", "cancelled", "failed_initialization", "failed_final_synthesis",
    "failed_report_validation",
}
TERMINAL_PREFIX = "failed_round_"


def artifact_path(workspace: str, name: str) -> Optional[str]:
    relative = ARTIFACT_PATHS.get(name)
    return os.path.join(workspace, relative) if relative else None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _terminal(config_status: str) -> bool:
    return config_status in TERMINAL_STATUSES or config_status.startswith(TERMINAL_PREFIX)


class WorkspaceOutsideRoot(PermissionError):
    """A user-supplied workspace path escaped the allowed root (安全围栏)."""


class RunCancelled(RuntimeError):
    """Raised between agent steps when a debate cancellation was requested."""

    def __init__(self, step_id: str = ""):
        self.step_id = step_id
        super().__init__(f"debate cancelled at step {step_id or '(between steps)'}")


class CancellableRunner:
    """Cooperative cancellation wrapper (v3.1 安全边界).

    Python threads cannot be killed, so cancellation happens at the existing
    ``AgentRunner`` seam: checked *before and after* every dispatched agent
    step. Deterministic steps between dispatches are fast, so this cancels a
    debate at step granularity without touching the graph.
    """

    runtime = "cancellable"

    def __init__(self, inner, cancel_event: threading.Event):
        self.inner = inner
        self.cancel_event = cancel_event

    def run(self, step_id: str, prompt: str, model_tier: str = "balanced",
            timeout_sec: int = 300, context=None):
        if self.cancel_event.is_set():
            raise RunCancelled(step_id)
        result = self.inner.run(step_id, prompt, model_tier=model_tier,
                                timeout_sec=timeout_sec, context=context)
        if self.cancel_event.is_set():
            raise RunCancelled(step_id)
        return result


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
    cancel_event: threading.Event = field(default_factory=threading.Event)
    version: int = 0  # bumped on every state change; lets WS clients detect updates


class DebateService:
    """Runs debates in background threads and exposes their live state."""

    def __init__(self, runner_factory: Optional[Callable[[], Any]] = None, runs_root: str = "/tmp",
                 workspace_root: Optional[str] = None):
        self._runs: dict[str, DebateRun] = {}
        self._lock = threading.Lock()
        self._runner_factory = runner_factory  # None → default get_runner()
        self._runs_root = runs_root
        # 安全围栏: user-supplied workspace paths must resolve inside this root.
        root = os.path.realpath(workspace_root or runs_root)
        os.makedirs(root, exist_ok=True)
        self.workspace_root = root

    def _confine_workspace(self, workspace: str) -> str:
        """Resolve a user-supplied workspace and enforce the allowed root."""
        resolved = os.path.realpath(os.path.abspath(workspace))
        if os.path.commonpath([resolved, self.workspace_root]) != self.workspace_root:
            raise WorkspaceOutsideRoot(
                f"workspace {workspace!r} is outside the allowed root {self.workspace_root!r}"
            )
        return resolved

    # -- lifecycle -----------------------------------------------------------

    def start(self, request) -> DebateRun:
        resume = bool(getattr(request, "resume", False))
        if request.workspace:
            workspace = self._confine_workspace(request.workspace)
        else:
            workspace = os.path.join(self._runs_root, "debate-" + uuid.uuid4().hex[:8])
            os.makedirs(workspace, exist_ok=True)
        if not os.path.exists(config_path(workspace)):
            if resume:
                raise FileNotFoundError(
                    f"cannot resume: no workspace checkpoint at {workspace}"
                )
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
            status="resuming" if resume else "running",
            started_at=_now(),
        )
        run.thread = threading.Thread(
            target=self._execute, args=(run, opts, resume), name=f"debate-{run.debate_id}", daemon=True,
        )
        with self._lock:
            self._runs[run.debate_id] = run
        run.thread.start()
        return run

    def _execute(self, run: DebateRun, opts: DebateOptions, resume: bool = False) -> None:
        from ..models.registry import get_runner

        try:
            inner = self._runner_factory() if self._runner_factory else get_runner()
            runner = CancellableRunner(inner, run.cancel_event)
            final_state = run_debate(run.workspace, opts, runner=runner, resume=resume)
            run.status = str(final_state.get("status", "complete"))
        except RunCancelled:
            run.status = "cancelled"
            run.error = None
            update_config(run.workspace, {"status": "cancelled"})
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
        """Refresh run.status from workspace config while the debate runs.

        While the run thread is alive only *non-terminal* config statuses are
        adopted — a terminal value in config.json is a checkpoint from a
        previous run and must not resurrect into the new run object. Once the
        thread has finished, ``run.status`` (set by ``_execute``) is the sole
        authority.
        """
        if run.thread is not None and run.thread.is_alive():
            cfg_status = self._config_status(run.workspace)
            if cfg_status and cfg_status != run.status and not _terminal(cfg_status):
                run.status = cfg_status
                run.version += 1

    def cancel(self, debate_id: str) -> tuple[DebateRun, bool]:
        """Request cooperative cancellation. Returns (run, was_running)."""
        run = self.get(debate_id)
        if run is None:
            raise KeyError(debate_id)
        was_running = not _terminal(run.status) and not run.finished_at
        if was_running:
            run.cancel_event.set()
            run.status = "cancelling"
            run.version += 1
        return run, was_running

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
        # Seed from the checkpoint so a stale terminal status from a previous
        # run is not re-emitted; the WS snapshot already carries the state.
        last_status: Optional[str] = self._config_status(run.workspace)

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
