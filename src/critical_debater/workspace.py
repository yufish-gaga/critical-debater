"""Workspace layout, config, and audit-trail helpers.

Python port of the v2 bash helpers (``init-workspace.sh``, ``append-audit.sh``)
and the JSON/config utilities inside ``debate_orchestrator_generic.py``.
The workspace directory layout and ``logs/audit_trail.jsonl`` semantics are
kept byte-compatible with v2 so both orchestrators can operate on the same
workspace.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Audit actions whose dedupe key is (action, round); all others dedupe by
# (action, details). Ported from append-audit.sh.
_LIFECYCLE_AUDIT_ACTIONS = {"pro_turn_complete", "con_turn_complete", "judge_ruling_complete"}


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def workspace_path(workspace: str, *parts: str) -> str:
    return os.path.join(workspace, *parts)


def read_json(filepath: str) -> Any:
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def read_json_or(filepath: str, default: Any) -> Any:
    if not os.path.exists(filepath):
        return default
    try:
        return read_json(filepath)
    except (json.JSONDecodeError, OSError):
        return default


def write_json(filepath: str, data: Any) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def config_path(workspace: str) -> str:
    return os.path.join(workspace, "config.json")


def load_config(workspace: str) -> dict:
    return read_json(config_path(workspace))


def update_config(workspace: str, updates: dict) -> dict:
    path = config_path(workspace)
    config = read_json(path)
    config.update(updates)
    config["updated_at"] = timestamp()
    write_json(path, config)
    return config


def audit_file(workspace: str) -> str:
    return os.path.join(workspace, "logs", "audit_trail.jsonl")


def read_audit(workspace: str) -> list[dict]:
    entries: list[dict] = []
    path = audit_file(workspace)
    if not os.path.exists(path):
        return entries
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _audit_key(entry: dict) -> tuple:
    if entry.get("action") in _LIFECYCLE_AUDIT_ACTIONS:
        return (entry["action"], (entry.get("details") or {}).get("round"))
    return (entry.get("action"), json.dumps(entry.get("details") or {}, sort_keys=True, ensure_ascii=False))


def append_audit(workspace: str, action: str, details: dict) -> None:
    """Atomically append a JSONL audit entry, deduplicating repeats (v2 semantics)."""
    entry = {"timestamp": timestamp(), "action": action, "details": details}
    path = audit_file(workspace)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    existing_keys = {_audit_key(e) for e in read_audit(workspace)}
    if _audit_key(entry) in existing_keys:
        return

    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as tmp_f:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                with open(path, encoding="utf-8") as src:
                    shutil_copy(src, tmp_f)
            tmp_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def shutil_copy(src_file, dst_file) -> None:
    for line in src_file:
        dst_file.write(line if line.endswith("\n") else line + "\n")


def init_workspace(
    workspace: str,
    topic: str,
    rounds: int,
    depth: str = "standard",
    mode: str = "balanced",
    evidence_refresh: str = "hybrid",
    language: str = "bilingual",
) -> None:
    """Create the workspace directory structure and seed files (port of init-workspace.sh)."""
    ws = Path(workspace)
    for sub in ("evidence", "claims", "rounds", "reports", "logs"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    for i in range(1, rounds + 1):
        (ws / "rounds" / f"round_{i}").mkdir(parents=True, exist_ok=True)

    now = timestamp()
    write_json(
        config_path(workspace),
        {
            "topic": topic,
            "round_count": rounds,
            "depth": depth,
            "mode": mode,
            "evidence_refresh": evidence_refresh,
            "language": language,
            "current_round": 0,
            "status": "initialized",
            "created_at": now,
            "updated_at": now,
        },
    )
    write_json(os.path.join(workspace, "evidence", "evidence_store.json"), [])
    write_json(os.path.join(workspace, "claims", "claim_ledger.json"), [])
    Path(audit_file(workspace)).touch()

    append_audit(workspace, "workspace_initialized", {"topic": topic, "rounds": rounds})


def ensure_workspace_config_defaults(workspace: str, defaults: dict) -> Optional[dict]:
    """Backfill missing config fields for legacy workspaces.

    Returns the applied updates (empty dict when nothing changed), mirroring
    ``ensure_workspace_config_defaults`` in the v2 orchestrator.
    """
    path = config_path(workspace)
    if not os.path.exists(path):
        return None

    config = read_json(path)
    updates = {}
    for key, value in defaults.items():
        if not config.get(key):
            updates[key] = value
    if updates:
        update_config(workspace, updates)
        append_audit(workspace, "config_migrated", {"updates": updates})
    return updates
