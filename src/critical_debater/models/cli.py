"""CLI-based agent runners (Phase 1 transport).

Port of ``dispatch_agent`` from the v2 orchestrator. Capabilities run as
subprocesses of the detected agent CLI; the ``DONE:<step_id>`` marker in
stdout marks an explicit success (a zero exit code is accepted as implicit
success, matching v2).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from ..workspace import timestamp
from .base import StepResult

# Per-step timeout floors for Codex, which is web-heavy on ingest/synthesis
# steps and consistently exceeds the default in practice (v2 behavior).
CODEX_TIMEOUT_FLOORS: tuple[tuple[str, int], ...] = (
    ("source_ingest", 1200),
    ("freshness_check", 600),
    ("debate_turn_", 900),
    ("judge_audit_", 900),
    ("final_synthesis", 1800),
)


def detect_runtime() -> str:
    """Detect which agent runtime is available. Priority: env override > codex > claude."""
    forced = os.environ.get("DEBATER_RUNTIME", "").strip().lower()
    if forced in {"codex", "claude"}:
        return forced
    for cmd, name in [("codex", "codex"), ("claude", "claude")]:
        if shutil.which(cmd):
            return name
    return "none"


def effective_timeout(step_id: str, runtime: str, timeout_sec: int) -> int:
    if runtime != "codex":
        return timeout_sec
    for prefix, floor in CODEX_TIMEOUT_FLOORS:
        if step_id.startswith(prefix):
            return max(timeout_sec, floor)
    return timeout_sec


def _decode(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore")
    return value or ""


class ClaudeCliRunner:
    """Dispatch a capability prompt via ``claude -p <prompt> --model <model>``."""

    runtime = "claude"

    def run(self, step_id: str, prompt: str, model_tier: str = "balanced",
            timeout_sec: int = 300) -> StepResult:
        from .registry import resolve_model

        model = resolve_model(model_tier, self.runtime)
        cmd = ["claude", "-p", prompt, "--model", model]
        return _execute(step_id, cmd, timeout_sec, self.runtime)


class CodexCliRunner:
    """Dispatch a capability prompt via ``codex exec`` with workspace-write sandbox."""

    runtime = "codex"

    def run(self, step_id: str, prompt: str, model_tier: str = "balanced",
            timeout_sec: int = 300) -> StepResult:
        from .registry import resolve_model

        model = resolve_model(model_tier, self.runtime)
        timeout_sec = effective_timeout(step_id, self.runtime, timeout_sec)
        cmd = [
            "codex", "exec",
            "-c", 'model_reasoning_effort="medium"',
            "--sandbox", "workspace-write",
            "--color", "never",
            "--model", model,
            prompt,
        ]
        return _execute(step_id, cmd, timeout_sec, self.runtime)


def _execute(step_id: str, cmd: list[str], timeout_sec: int, runtime: str) -> StepResult:
    print(f"[{timestamp()}] Executing step: {step_id} (runtime: {runtime})")
    print(f"[{timestamp()}] Prompt length: {len(cmd[-1])} chars")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired as e:
        detail = (_decode(e.stderr) or _decode(e.stdout) or "").strip()
        reason = f"Step timed out after {timeout_sec}s"
        if detail:
            reason += f"; partial output: {detail[:400]}"
        print(f"[{timestamp()}] Step {step_id} TIMED OUT after {timeout_sec}s", file=sys.stderr)
        return StepResult(step_id=step_id, success=False, error_type="timeout", reason=reason)
    except FileNotFoundError:
        msg = f"Runtime '{runtime}' not found in PATH"
        print(f"[{timestamp()}] ERROR: {msg}", file=sys.stderr)
        return StepResult(step_id=step_id, success=False, error_type="runtime_missing", reason=msg)

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode != 0:
        print(f"[{timestamp()}] Step {step_id} exited with code {result.returncode}", file=sys.stderr)
        if stderr:
            print(f"[{timestamp()}] stderr: {stderr[:500]}", file=sys.stderr)
        return StepResult(
            step_id=step_id,
            success=False,
            error_type="nonzero_exit",
            reason=(stderr[:500] or "subprocess returned non-zero exit"),
            exit_code=result.returncode,
        )

    if f"DONE:{step_id}" in stdout:
        print(f"[{timestamp()}] Step {step_id} completed successfully")
        return StepResult(step_id=step_id, success=True, exit_code=result.returncode)

    print(f"[{timestamp()}] Step {step_id} finished (no DONE marker, exit code {result.returncode})")
    # Runtime may succeed without explicit marker.
    return StepResult(step_id=step_id, success=True, exit_code=result.returncode)
