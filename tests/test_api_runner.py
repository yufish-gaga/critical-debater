"""Tests for LLMAgentRunner step handlers and the API-driven end-to-end run."""

from __future__ import annotations

import os

import pytest

from critical_debater.config import DebateOptions
from critical_debater.errors import DebateStepFailure
from critical_debater.graph.runner import run_debate
from critical_debater.models.api_runner import LLMAgentRunner
from critical_debater.models.provider import ProviderError
from critical_debater.validation import validate_debate_report_file, validate_json_file
from critical_debater.workspace import read_json, read_audit

from fake_provider import (
    FakeRegistry,
    FakeSearch,
    api_runner_scripts,
    debate_turn_response,
    fresh_queries,
    ledger_response,
    search_result_payload,
)


def make_runner(scripts: dict, search: FakeSearch | None = None) -> LLMAgentRunner:
    return LLMAgentRunner(FakeRegistry(scripts), search or FakeSearch())


# --- individual step handlers ------------------------------------------------


def test_source_ingest_appends_contract_valid_evidence(workspace):
    runner = make_runner({"ingest": [fresh_queries(), search_result_payload(0, 3)]})
    result = runner.run(
        "source_ingest_round_0",
        f"Execute source-ingest.md. Workspace: {workspace}",
        context={"workspace": workspace, "topic": "Test topic", "mode": "broad",
                 "round": 0, "num_queries": 2},
    )
    assert result.success, result.reason
    store = read_json(os.path.join(workspace, "evidence", "evidence_store.json"))
    assert len(store) == 3
    first = store[0]
    assert first["evidence_id"].startswith("evi_")
    assert first["evidence_id"] == f"evi_{first['hash'][:8]}"
    assert first["discovered_by"] == "orchestrator"
    assert first["discovered_at_round"] == 0
    assert first["search_context"] == "initial_broad"
    assert first["credibility_tier"] in {"tier1_authoritative", "tier2_reputable",
                                         "tier3_general", "tier4_social"}


def test_source_ingest_dedupes_rerun(workspace):
    script = {"ingest": [fresh_queries(), search_result_payload(0, 2),
                         fresh_queries(), search_result_payload(0, 2)]}
    runner = make_runner(script)
    ctx = {"workspace": workspace, "topic": "T", "mode": "broad", "round": 0}
    runner.run("source_ingest_round_0", f"w: {workspace}", context=ctx)
    result = runner.run("source_ingest_round_0", f"w: {workspace}", context=ctx)
    assert result.success
    store = read_json(os.path.join(workspace, "evidence", "evidence_store.json"))
    assert len(store) == 2  # identical batch → deduped


def test_freshness_check_applies_updates(workspace):
    from fake_agent import evidence_item, _write_json

    _write_json(os.path.join(workspace, "evidence", "evidence_store.json"),
                [evidence_item(1), evidence_item(2)])
    script = {"ingest": [{"updates": [{"evidence_id": "evi_test0001",
                                       "freshness_status": "stale"}]}]}
    runner = make_runner(script)
    result = runner.run("freshness_check_0", f"w: {workspace}",
                        context={"workspace": workspace})
    assert result.success
    store = read_json(os.path.join(workspace, "evidence", "evidence_store.json"))
    statuses = {e["evidence_id"]: e["freshness_status"] for e in store}
    assert statuses["evi_test0001"] == "stale"
    assert statuses["evi_test0002"] == "current"


def test_debate_turn_writes_valid_turn(workspace):
    from fake_provider import debate_turn_response

    runner = make_runner({"pro": [debate_turn_response(1, "pro")]})
    result = runner.run(
        "debate_turn_pro_round_1", f"w: {workspace}",
        context={"workspace": workspace, "topic": "T", "side": "pro", "round": 1,
                 "mode": "balanced", "speculation": "moderate", "depth": "standard"},
    )
    assert result.success, result.reason
    ok, msg = validate_json_file(
        os.path.join(workspace, "rounds", "round_1", "pro_turn.json"), "pro_turn"
    )
    assert ok, msg


def test_judge_audit_writes_ruling(workspace):
    from fake_provider import judge_response

    runner = make_runner({"judge": [judge_response(1)]})
    result = runner.run("judge_audit_round_1", f"w: {workspace}",
                        context={"workspace": workspace, "round": 1})
    assert result.success
    ok, msg = validate_json_file(
        os.path.join(workspace, "rounds", "round_1", "judge_ruling.json"), "judge_ruling"
    )
    assert ok, msg


def test_claim_ledger_update_merges(workspace):
    from fake_agent import _write_json
    from fake_provider import judge_response, ledger_response

    ruling = judge_response(1)
    _write_json(os.path.join(workspace, "rounds", "round_1", "judge_ruling.json"), ruling)
    _write_json(os.path.join(workspace, "claims", "claim_ledger.json"), [
        {"claim_id": "clm_1_pro_1", "round": 1, "speaker": "pro", "status": "unverified",
         "claim_text": "old", "evidence_ids": []},
    ])
    runner = make_runner({"ingest": [ledger_response(1)]})
    result = runner.run("claim_ledger_update_round_1", f"w: {workspace}",
                        context={"workspace": workspace, "round": 1})
    assert result.success
    ledger = read_json(os.path.join(workspace, "claims", "claim_ledger.json"))
    ids = {c["claim_id"] for c in ledger}
    assert "clm_1_pro_1" in ids and "clm_1_con_1" in ids
    by_id = {c["claim_id"]: c for c in ledger}
    assert by_id["clm_1_pro_1"]["status"] == "verified"
    assert by_id["clm_1_pro_1"]["last_verified_at"]


def test_unsupported_step_fails_cleanly(workspace):
    runner = make_runner({})
    result = runner.run("mystery_step", f"w: {workspace}",
                        context={"workspace": workspace})
    assert not result.success
    assert result.error_type == "unsupported_step"


def test_provider_error_wrapped(workspace):
    from fake_agent import _write_json, evidence_item

    _write_json(os.path.join(workspace, "evidence", "evidence_store.json"), [evidence_item(1)])

    class ExplodingRegistry:
        default_provider = "fake"

        def resolve(self, role, tier="balanced"):
            class P:
                name = "fake"

                def chat(self, system, user, timeout_sec=None):
                    raise ProviderError("api key invalid")

            return P(), "m"

    runner = LLMAgentRunner(ExplodingRegistry(), FakeSearch())
    result = runner.run("freshness_check_0", f"w: {workspace}",
                        context={"workspace": workspace, "topic": "T"})
    assert not result.success
    assert result.error_type == "provider_error"
    assert "api key invalid" in result.reason


def test_context_falls_back_to_prompt_workspace():
    from critical_debater.models.api_runner import _workspace_from_prompt

    assert _workspace_from_prompt("do it Workspace: /tmp/ws") == "/tmp/ws"
    assert _workspace_from_prompt("do it workspace=/tmp/ws2") == "/tmp/ws2"
    with pytest.raises(ValueError):
        _workspace_from_prompt("nothing here")


# --- full graph end-to-end through the API runner ----------------------------


def test_full_debate_via_api_runner(workspace):
    opts = DebateOptions(topic="Test topic", rounds=2, min_evidence=3)
    # 2 ingest batches (round 0 + round 2 refresh): 3 then 1 items.
    runner = make_runner(api_runner_scripts(rounds=2, evidence_batches=[3, 1]))

    final_state = run_debate(workspace, opts, runner=runner)
    assert final_state["status"] == "complete"
    assert final_state["model_provider"].startswith("api")

    store = read_json(os.path.join(workspace, "evidence", "evidence_store.json"))
    assert len(store) == 3 + 1  # round-0 batch + round-2 refresh batch

    for path, schema in [
        ("rounds/round_1/pro_turn.json", "pro_turn"),
        ("rounds/round_1/con_turn.json", "con_turn"),
        ("rounds/round_1/judge_ruling.json", "judge_ruling"),
        ("rounds/round_2/pro_turn.json", "pro_turn"),
        ("rounds/round_2/judge_ruling.json", "judge_ruling"),
        ("reports/final_report.json", "final_report"),
    ]:
        ok, msg = validate_json_file(os.path.join(workspace, path), schema)
        assert ok, f"{path}: {msg}"

    ok, msg = validate_debate_report_file(os.path.join(workspace, "reports", "debate_report.md"))
    assert ok, msg

    cfg = read_json(os.path.join(workspace, "config.json"))
    assert cfg["status"] == "complete"

    actions = [e["action"] for e in read_audit(workspace)]
    assert "step_failed" not in actions
    assert "per_round_evidence_ingest" in actions  # hybrid refresh ran in round 2
    assert "report_generated" in actions


def test_full_debate_api_provider_error_fails_round(workspace):
    from critical_debater.models.provider import ProviderError as PE

    opts = DebateOptions(topic="Test topic", rounds=1, min_evidence=3)
    script = {"ingest": [fresh_queries(), search_result_payload(0, 3), {"updates": []},
                         ledger_response(1)],
              "pro": [debate_turn_response(1, "pro")],
              "con": [debate_turn_response(1, "con")],
              "judge": [PE("judge provider unavailable")]}
    runner = LLMAgentRunner(FakeRegistry(script), FakeSearch())
    with pytest.raises(DebateStepFailure) as excinfo:
        run_debate(workspace, opts, runner=runner)
    # Judge step fails with a provider error → hard stop at failed_round_1.
    assert excinfo.value.status == "failed_round_1"
    assert excinfo.value.error_type == "provider_error"
