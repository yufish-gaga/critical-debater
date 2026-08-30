"""Unit tests for deterministic helpers: audit dedupe, evidence merge, claim consistency."""

from __future__ import annotations

import json
import os

from critical_debater.claims import verify_claim_ledger_consistency
from critical_debater.evidence import merge_new_evidence
from critical_debater.workspace import append_audit, read_audit, update_config

from fake_agent import _write_json, evidence_item, valid_judge_ruling


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- audit trail -------------------------------------------------------------

def test_append_audit_dedupes_details_key(workspace):
    append_audit(workspace, "evidence_added", {"round": 0, "mode": "broad"})
    append_audit(workspace, "evidence_added", {"round": 0, "mode": "broad"})
    entries = read_audit(workspace)
    assert len([e for e in entries if e["action"] == "evidence_added"]) == 1


def test_append_audit_lifecycle_dedupes_by_round(workspace):
    append_audit(workspace, "pro_turn_complete", {"round": 1})
    append_audit(workspace, "pro_turn_complete", {"round": 1})
    append_audit(workspace, "pro_turn_complete", {"round": 2})
    entries = [e for e in read_audit(workspace) if e["action"] == "pro_turn_complete"]
    assert [e["details"]["round"] for e in entries] == [1, 2]


def test_update_config_sets_updated_at(workspace):
    cfg = update_config(workspace, {"status": "in_progress"})
    assert cfg["status"] == "in_progress"
    assert cfg["updated_at"]


# --- evidence merge ----------------------------------------------------------

def test_merge_new_evidence_dedupes_and_tags(workspace):
    round_dir = os.path.join(workspace, "rounds", "round_1")
    store = [evidence_item(1)]
    _write_json(os.path.join(workspace, "evidence", "evidence_store.json"), store)

    _write_json(os.path.join(round_dir, "pro_turn.json"), {
        "round": 1, "side": "pro", "arguments": [], "rebuttals": [],
        "new_evidence": [evidence_item(1), evidence_item(2)],
    })
    _write_json(os.path.join(round_dir, "con_turn.json"), {
        "round": 1, "side": "con", "arguments": [], "rebuttals": [],
        "new_evidence": [evidence_item(2), evidence_item(3)],
    })

    total = merge_new_evidence(workspace, 1)
    merged = _read(os.path.join(workspace, "evidence", "evidence_store.json"))
    assert total == 3
    assert len(merged) == 3
    assert merged[1]["discovered_by"] == "pro"
    assert merged[1]["discovered_at_round"] == 1
    assert merged[2]["discovered_by"] == "con"
    actions = [e["action"] for e in read_audit(workspace)]
    assert "evidence_merged_from_turn" in actions


# --- claim consistency -------------------------------------------------------

def test_consistency_direct_claim_id_ok(workspace):
    ruling = valid_judge_ruling(1)
    _write_json(os.path.join(workspace, "rounds", "round_1", "judge_ruling.json"), ruling)
    _write_json(os.path.join(workspace, "claims", "claim_ledger.json"), [
        {"claim_id": "clm_1_pro_1", "round": 1, "speaker": "pro", "status": "verified"},
        {"claim_id": "clm_1_con_1", "round": 1, "speaker": "con", "status": "contested"},
    ])
    result = verify_claim_ledger_consistency(workspace, 1)
    assert result.success, result.reason
    assert [e["details"]["resolved_by"] for e in read_audit(workspace)
            if e["action"] == "claim_verification_applied"] == ["direct_claim_id", "direct_claim_id"]


def test_consistency_legacy_target_index(workspace):
    ruling = valid_judge_ruling(1)
    ruling["verification_results"] = [
        {"target": "pro", "claim_index": 1, "new_status": "verified", "reason": "ok"}
    ]
    _write_json(os.path.join(workspace, "rounds", "round_1", "judge_ruling.json"), ruling)
    _write_json(os.path.join(workspace, "claims", "claim_ledger.json"), [
        {"claim_id": "clm_1_pro_1", "round": 1, "speaker": "pro", "status": "verified"},
    ])
    result = verify_claim_ledger_consistency(workspace, 1)
    assert result.success, result.reason


def test_consistency_status_mismatch_fails(workspace):
    ruling = valid_judge_ruling(1)
    _write_json(os.path.join(workspace, "rounds", "round_1", "judge_ruling.json"), ruling)
    _write_json(os.path.join(workspace, "claims", "claim_ledger.json"), [
        {"claim_id": "clm_1_pro_1", "round": 1, "speaker": "pro", "status": "unverified"},
    ])
    result = verify_claim_ledger_consistency(workspace, 1)
    assert not result.success
    assert result.error_type == "claim_status_mismatch"


def test_consistency_missing_claim_fails(workspace):
    ruling = valid_judge_ruling(1)
    _write_json(os.path.join(workspace, "rounds", "round_1", "judge_ruling.json"), ruling)
    _write_json(os.path.join(workspace, "claims", "claim_ledger.json"), [])
    result = verify_claim_ledger_consistency(workspace, 1)
    assert result.error_type == "claim_missing"


def test_consistency_missing_reasoning_fails(workspace):
    ruling = valid_judge_ruling(1)
    ruling["verification_results"][0]["reasoning"] = ""
    _write_json(os.path.join(workspace, "rounds", "round_1", "judge_ruling.json"), ruling)
    _write_json(os.path.join(workspace, "claims", "claim_ledger.json"), [
        {"claim_id": "clm_1_pro_1", "round": 1, "speaker": "pro", "status": "verified"},
    ])
    result = verify_claim_ledger_consistency(workspace, 1)
    assert result.error_type == "invalid_judge_output"
