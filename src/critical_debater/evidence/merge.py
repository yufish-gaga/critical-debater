"""Merge ``new_evidence`` from Pro/Con turn outputs into the evidence store.

Port of ``merge_new_evidence`` in the v2 orchestrator: dedupe by
(url, hash), tag provenance (``discovered_by`` / ``discovered_at_round``),
write the store back, and append the ``evidence_merged_from_turn`` audit
event.
"""

from __future__ import annotations

import os

from ..workspace import append_audit, read_json, timestamp, write_json


def evidence_store_path(workspace: str) -> str:
    return os.path.join(workspace, "evidence", "evidence_store.json")


def load_evidence_store(workspace: str) -> list[dict]:
    path = evidence_store_path(workspace)
    if not os.path.exists(path):
        return []
    return read_json(path)


def merge_new_evidence(workspace: str, round_num: int) -> int:
    """Merge new evidence from both sides' turn files. Returns store size."""
    evidence_store = load_evidence_store(workspace)
    existing_keys = {(e.get("url", ""), e.get("hash", "")) for e in evidence_store}

    for side in ["pro", "con"]:
        turn_path = os.path.join(workspace, "rounds", f"round_{round_num}", f"{side}_turn.json")
        if not os.path.exists(turn_path):
            continue
        turn = read_json(turn_path)
        for item in turn.get("new_evidence", []):
            key = (item.get("url", ""), item.get("hash", ""))
            if key in existing_keys:
                continue
            item["discovered_by"] = side
            item["discovered_at_round"] = round_num
            evidence_store.append(item)
            existing_keys.add(key)

    write_json(evidence_store_path(workspace), evidence_store)
    append_audit(workspace, "evidence_merged_from_turn", {
        "round": round_num,
        "total_items": len(evidence_store),
    })
    print(f"[{timestamp()}] Evidence store now holds {len(evidence_store)} items after round {round_num}")
    return len(evidence_store)
