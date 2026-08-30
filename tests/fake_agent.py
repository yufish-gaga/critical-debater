"""Scripted fake agent runner for hermetic graph tests.

Simulates the v2 capability contract: each dispatched step writes the
artifact files the real agent CLI would produce. Behavior knobs let tests
exercise retry loops, hard failures, and the final-synthesis fallback.
"""

from __future__ import annotations

import json
import os

from critical_debater.models.base import StepResult


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evidence_item(idx: int, url_suffix: str = "", **overrides) -> dict:
    item = {
        "evidence_id": f"evi_test{idx:04d}",
        "source_type": "web",
        "url": f"https://example.com/src{idx}{url_suffix}",
        "publisher": "Example News",
        "published_at": "2026-08-01T00:00:00Z",
        "retrieved_at": "2026-08-30T00:00:00Z",
        "snippet": f"Snippet {idx}",
        "hash": f"hash{idx}",
        "credibility_tier": "tier2_reputable",
        "freshness_status": "current",
        "evidence_track": "fact",
    }
    item.update(overrides)
    return item


def valid_turn(round_num: int, side: str, new_evidence: list | None = None) -> dict:
    return {
        "round": round_num,
        "side": side,
        "arguments": [
            {
                "claim_text": f"{side} argument for round {round_num}",
                "claim_type": "fact",
                "evidence_ids": ["evi_test0001"],
                "reasoning_chain": {
                    "observed_facts": "facts",
                    "mechanism": "mechanism",
                    "scenario_implication": "implication",
                    "trigger_conditions": "triggers",
                    "falsification_conditions": "falsifiers",
                },
            }
        ],
        "rebuttals": [],
        "new_evidence": new_evidence or [],
    }


def valid_judge_ruling(round_num: int) -> dict:
    return {
        "round": round_num,
        "verification_results": [
            {
                "claim_id": f"clm_{round_num}_pro_1",
                "original_status": "unverified",
                "new_status": "verified",
                "reasoning": "Cross-source confirmed.",
            },
            {
                "claim_id": f"clm_{round_num}_con_1",
                "original_status": "unverified",
                "new_status": "contested",
                "reasoning": "Sources conflict.",
            },
        ],
        "causal_validity_flags": [],
        "mandatory_response_points": [
            {
                "point_id": f"mrp_{round_num}_1",
                "target": "con",
                "point": "Address the conflict.",
                "reason": "Judge requires response.",
            }
        ],
        "historical_wisdom_assessment": [],
        "round_summary": f"Round {round_num} summary.",
    }


def ledger_for_ruling(ruling: dict) -> list[dict]:
    ledger = []
    for vr in ruling.get("verification_results", []):
        parts = vr["claim_id"].split("_")
        ledger.append({
            "claim_id": vr["claim_id"],
            "round": int(parts[1]),
            "speaker": parts[2],
            "claim_type": "fact",
            "claim_text": f"claim {vr['claim_id']}",
            "evidence_ids": ["evi_test0001"],
            "status": vr["new_status"],
        })
    return ledger


def _extract_workspace(prompt: str) -> str:
    # Prompts end with either "Workspace: <path>" or "workspace=<path>".
    for marker in ("Workspace: ", "workspace="):
        if marker in prompt:
            return prompt.rsplit(marker, 1)[1].strip()
    raise ValueError(f"No workspace in prompt: {prompt}")


class FakeScriptedRunner:
    """Writes contract-valid artifacts for every dispatched step."""

    runtime = "fake"

    def __init__(
        self,
        initial_evidence: int = 10,
        retry_evidence: int = 0,
        valid_turns: bool = True,
        judge_writes_ruling: bool = True,
        final_synthesis_ok: bool = True,
        final_synthesis_writes_json: bool = True,
        report_md_fixture: str | None = None,
        evidence_per_turn: int = 1,
    ):
        self.calls: list[tuple[str, str]] = []
        self.initial_evidence = initial_evidence
        self.retry_evidence = retry_evidence
        self.valid_turns = valid_turns
        self.judge_writes_ruling = judge_writes_ruling
        self.final_synthesis_ok = final_synthesis_ok
        self.final_synthesis_writes_json = final_synthesis_writes_json
        self.report_md_fixture = report_md_fixture
        self.evidence_per_turn = evidence_per_turn
        self._evidence_seq = 0

    # -- helpers ---------------------------------------------------------

    def _add_evidence(self, workspace: str, count: int, url_suffix: str = "") -> None:
        if count <= 0:
            return
        path = os.path.join(workspace, "evidence", "evidence_store.json")
        store = _read_json(path, [])
        for _ in range(count):
            self._evidence_seq += 1
            store.append(evidence_item(self._evidence_seq, url_suffix))
        _write_json(path, store)

    def _record(self, step_id: str, model_tier: str) -> None:
        self.calls.append((step_id, model_tier))
        print(f"[fake] dispatch {step_id} (tier={model_tier})")

    # -- AgentRunner protocol --------------------------------------------

    def run(self, step_id: str, prompt: str, model_tier: str = "balanced",
            timeout_sec: int = 300, context: dict | None = None) -> StepResult:
        self._record(step_id, model_tier)
        if context and context.get("workspace"):
            workspace = context["workspace"]
        else:
            workspace = _extract_workspace(prompt)

        if step_id.startswith("source_ingest_round_0"):
            self._add_evidence(workspace, self.initial_evidence)
            return StepResult(step_id=step_id, success=True, exit_code=0)

        if step_id.startswith("source_ingest_retry_"):
            self._add_evidence(workspace, self.retry_evidence)
            return StepResult(step_id=step_id, success=True, exit_code=0)

        if step_id.startswith("freshness_check"):
            return StepResult(step_id=step_id, success=True, exit_code=0)

        if step_id.startswith("debate_turn_pro_round_") or step_id.startswith("debate_turn_con_round_"):
            side = "pro" if "_pro_" in step_id else "con"
            round_num = int(step_id.rsplit("_round_", 1)[1].split("_")[0])
            if self.valid_turns:
                new_evidence = []
                if self.evidence_per_turn:
                    for _ in range(self.evidence_per_turn):
                        self._evidence_seq += 1
                        new_evidence.append(evidence_item(self._evidence_seq, url_suffix=f"-{side}{round_num}"))
                _write_json(
                    os.path.join(workspace, "rounds", f"round_{round_num}", f"{side}_turn.json"),
                    valid_turn(round_num, side, new_evidence),
                )
            # invalid-turn simulation writes nothing, forcing missing_output failure
            return StepResult(step_id=step_id, success=True, exit_code=0)

        if step_id.startswith("judge_audit_round_"):
            round_num = int(step_id.rsplit("_", 1)[1])
            if self.judge_writes_ruling:
                ruling = valid_judge_ruling(round_num)
                _write_json(
                    os.path.join(workspace, "rounds", f"round_{round_num}", "judge_ruling.json"),
                    ruling,
                )
            return StepResult(step_id=step_id, success=True, exit_code=0)

        if step_id.startswith("claim_ledger_update_round_"):
            round_num = int(step_id.rsplit("_", 1)[1])
            ruling_path = os.path.join(workspace, "rounds", f"round_{round_num}", "judge_ruling.json")
            ruling = _read_json(ruling_path, valid_judge_ruling(round_num))
            _write_json(
                os.path.join(workspace, "claims", "claim_ledger.json"),
                _read_json(os.path.join(workspace, "claims", "claim_ledger.json"), []) + ledger_for_ruling(ruling),
            )
            return StepResult(step_id=step_id, success=True, exit_code=0)

        if step_id == "final_synthesis":
            if self.final_synthesis_ok or self.final_synthesis_writes_json:
                report = {
                    "topic": "Test topic",
                    "total_rounds": 2,
                    "generated_at": "2026-08-30T00:00:00Z",
                    "verdict_summary": "ok",
                    "report_path": "reports/debate_report.md",
                    "verified_facts": ["fact one"],
                    "probable_conclusions": ["conclusion one"],
                    "contested_points": [],
                    "to_verify": ["item one"],
                    "scenario_outlook": {
                        "base_case": "base",
                        "upside_triggers": [],
                        "downside_triggers": [],
                        "falsification_conditions": [],
                    },
                    "watchlist_24h": [],
                }
                if self.final_synthesis_writes_json:
                    _write_json(os.path.join(workspace, "reports", "final_report.json"), report)
            if self.final_synthesis_ok and self.report_md_fixture:
                os.makedirs(os.path.join(workspace, "reports"), exist_ok=True)
                with open(self.report_md_fixture, encoding="utf-8") as src, open(
                    os.path.join(workspace, "reports", "debate_report.md"), "w", encoding="utf-8"
                ) as dst:
                    dst.write(src.read())
            return StepResult(
                step_id=step_id,
                success=self.final_synthesis_ok,
                error_type="" if self.final_synthesis_ok else "simulated_failure",
                reason="" if self.final_synthesis_ok else "final synthesis simulated failure",
            )

        return StepResult(step_id=step_id, success=True, exit_code=0)
