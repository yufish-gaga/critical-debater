"""Ensure judge verification results are reflected in the claim ledger.

Port of ``verify_claim_ledger_consistency`` from the v2 orchestrator,
including the three-way claim_id resolution (direct id, legacy
target+index, legacy text match) and the ``claim_verification_applied``
audit events.
"""

from __future__ import annotations

import os
from typing import Optional

from ..models.base import StepResult
from ..workspace import append_audit, read_json


def _normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _resolve_claim_id(vr: dict, ledger: list[dict], ledger_index: dict, round_num: int) -> tuple[Optional[str], str]:
    """Resolve claim_id from a judge verification row.

    Supports:
    - current contract: claim_id + new_status + reasoning
    - legacy contract: target + claim_index + status (+ reason)
    - legacy contract: claim_text substring match within same round/side
    """
    direct_claim_id = vr.get("claim_id")
    if direct_claim_id:
        return direct_claim_id, "direct_claim_id"

    target = (vr.get("target") or "").strip().lower()
    claim_index = vr.get("claim_index")
    if target in {"pro", "con"} and isinstance(claim_index, int):
        inferred = f"clm_{round_num}_{target}_{claim_index}"
        if inferred in ledger_index:
            return inferred, "legacy_target_index"

    claim_text = _normalize_text(vr.get("claim_text", ""))
    if claim_text:
        candidates = []
        for item in ledger:
            item_id = item.get("claim_id")
            if not item_id:
                continue
            if item.get("round") != round_num:
                continue
            if target in {"pro", "con"} and item.get("speaker") != target:
                continue
            item_text = _normalize_text(item.get("claim_text", ""))
            if not item_text:
                continue
            if claim_text in item_text or item_text in claim_text:
                candidates.append(item_id)
        if len(candidates) == 1:
            return candidates[0], "legacy_text_match"

    return None, "unresolved"


def verify_claim_ledger_consistency(workspace: str, round_num: int) -> StepResult:
    ledger_path = os.path.join(workspace, "claims", "claim_ledger.json")
    judge_path = os.path.join(workspace, "rounds", f"round_{round_num}", "judge_ruling.json")
    step_id = f"claim_consistency_round_{round_num}"

    if not os.path.exists(ledger_path):
        return StepResult(step_id=step_id, success=False, error_type="missing_output",
                          reason=f"Missing claim ledger: {ledger_path}")
    if not os.path.exists(judge_path):
        return StepResult(step_id=step_id, success=False, error_type="missing_output",
                          reason=f"Missing judge ruling: {judge_path}")

    ledger = read_json(ledger_path)
    judge = read_json(judge_path)
    verification_results = judge.get("verification_results", [])
    ledger_index = {item.get("claim_id"): item for item in ledger}

    for vr in verification_results:
        claim_id, resolved_by = _resolve_claim_id(vr, ledger, ledger_index, round_num)
        expected = vr.get("new_status") or vr.get("status")
        reasoning = (vr.get("reasoning") or vr.get("reason") or "").strip()

        if not claim_id or not expected:
            return StepResult(
                step_id=step_id,
                success=False,
                error_type="invalid_judge_output",
                reason=f"verification_results item missing resolvable claim_id/new_status: {vr}",
            )
        if not reasoning:
            return StepResult(
                step_id=step_id,
                success=False,
                error_type="invalid_judge_output",
                reason=f"verification_results missing reasoning for claim {claim_id}",
            )

        entry = ledger_index.get(claim_id)
        if entry is None:
            return StepResult(
                step_id=step_id,
                success=False,
                error_type="claim_missing",
                reason=f"claim_ledger missing claim_id {claim_id} from verification_results",
            )

        actual = entry.get("status")
        if actual != expected:
            return StepResult(
                step_id=step_id,
                success=False,
                error_type="claim_status_mismatch",
                reason=f"claim {claim_id}: expected status {expected}, found {actual}",
            )

        append_audit(workspace, "claim_verification_applied", {
            "round": round_num,
            "claim_id": claim_id,
            "expected_status": expected,
            "actual_status": actual,
            "resolved_by": resolved_by,
        })

    return StepResult(step_id=step_id, success=True, exit_code=0)
