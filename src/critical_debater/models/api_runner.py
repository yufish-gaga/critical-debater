"""API-backed agent runner (v3 Phase 2).

Executes the same capability steps as the CLI runners, but entirely in
process: the runner injects the capability instructions plus the workspace
context (evidence store, claim ledger, round artifacts) into the prompt,
calls the configured LLM provider, enforces a JSON output contract, and
writes the resulting artifacts back to the workspace.

Web search for source-ingest goes through the pluggable
:class:`~critical_debater.models.search.SearchProvider`. The
final bilingual ``debate_report.md`` is produced by the deterministic
renderer from ``final_report.json`` (the same fallback path v2 uses), which
guarantees Section 8 format validity without LLM guesswork.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from ..workspace import read_json_or, timestamp, write_json
from .base import Context, StepResult
from .provider import ProviderError, extract_json_object
from .search import NullSearchProvider, SearchProvider
from .registry import ProviderRegistry, build_registry, load_debate_config

_EVIDENCE_ALLOWED_TIERS = {
    "tier1_authoritative", "tier2_reputable", "tier3_general", "tier4_social",
}
_EVIDENCE_ALLOWED_TRACKS = {"fact", "reasoning"}
_EVIDENCE_ALLOWED_FRESHNESS = {"current", "stale", "timeless"}

_SYSTEM_TEMPLATE = (
    "You are the '{capability}' agent inside Critical Debater, a multi-agent "
    "adversarial debate pipeline with strict evidence handling. Follow these "
    "capability instructions exactly:\n\n{instructions}"
)

_JSON_FIX_SUFFIX = (
    "\n\nIMPORTANT: your previous reply was not a single valid JSON object. "
    "Reply with ONLY one JSON object and nothing else."
)


def _now_iso() -> str:
    return timestamp()


def _snippet_hash(snippet: str) -> str:
    return hashlib.sha256((snippet or "").encode("utf-8")).hexdigest()


def _truncate(text: Any, limit: int = 600) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "…"


def _evidence_context(store: list[dict], snippet_limit: int = 400) -> list[dict]:
    """Compact evidence view for prompt injection."""
    return [
        {
            "evidence_id": e.get("evidence_id"),
            "source_type": e.get("source_type"),
            "url": e.get("url"),
            "publisher": e.get("publisher"),
            "published_at": e.get("published_at"),
            "snippet": _truncate(e.get("snippet"), snippet_limit),
            "credibility_tier": e.get("credibility_tier"),
            "freshness_status": e.get("freshness_status"),
            "evidence_track": e.get("evidence_track"),
            "corroboration_status": e.get("corroboration_status"),
        }
        for e in store
        if isinstance(e, dict)
    ]


class LLMAgentRunner:
    """Run capability steps through configured LLM providers."""

    def __init__(self, registry: ProviderRegistry, search: Optional[SearchProvider] = None,
                 runtime_label: str = "api"):
        self.registry = registry
        self.search = search if search is not None else NullSearchProvider()
        self.runtime = runtime_label

    # ------------------------------------------------------------------
    # construction

    @classmethod
    def from_config(cls, config: dict | None = None) -> "LLMAgentRunner":
        cfg = config if config is not None else load_debate_config()
        registry = build_registry(cfg)
        from .search import build_search_provider

        search = build_search_provider(cfg.get("search"))
        return cls(registry, search, runtime_label=f"api:{registry.default_provider}")

    # ------------------------------------------------------------------
    # AgentRunner protocol

    def run(self, step_id: str, prompt: str, model_tier: str = "balanced",
            timeout_sec: int = 300, context: Optional[Context] = None) -> StepResult:
        context = dict(context or {})
        if not context.get("workspace"):
            context["workspace"] = _workspace_from_prompt(prompt)
        try:
            if step_id.startswith("source_ingest"):
                return self._source_ingest(step_id, context, model_tier, timeout_sec)
            if step_id.startswith("freshness_check"):
                return self._freshness_check(step_id, context, model_tier, timeout_sec)
            if step_id.startswith("debate_turn"):
                return self._debate_turn(step_id, context, model_tier, timeout_sec)
            if step_id.startswith("judge_audit"):
                return self._judge_audit(step_id, context, model_tier, timeout_sec)
            if step_id.startswith("claim_ledger_update"):
                return self._claim_ledger_update(step_id, context, model_tier, timeout_sec)
            if step_id == "final_synthesis":
                return self._final_synthesis(step_id, context, model_tier, timeout_sec)
            return StepResult(step_id=step_id, success=False,
                              error_type="unsupported_step",
                              reason=f"LLMAgentRunner cannot execute step {step_id}")
        except ProviderError as e:
            print(f"[{timestamp()}] Step {step_id} provider error: {e}", flush=True)
            return StepResult(step_id=step_id, success=False,
                              error_type="provider_error", reason=str(e)[:500])
        except (OSError, ValueError, KeyError) as e:
            print(f"[{timestamp()}] Step {step_id} runner error: {e}", flush=True)
            return StepResult(step_id=step_id, success=False,
                              error_type="runner_error", reason=f"{type(e).__name__}: {e}"[:500])

    # ------------------------------------------------------------------
    # LLM plumbing

    def _chat_json(self, step_id: str, capability: str, role: str, tier: str,
                   user_prompt: str, timeout_sec: int) -> dict:
        from ..paths import capability_path

        instructions = capability_path(capability).read_text(encoding="utf-8")
        system = _SYSTEM_TEMPLATE.format(capability=capability.replace(".md", ""), instructions=instructions)
        provider, model = self.registry.resolve(role, tier)
        print(f"[{timestamp()}] Step {step_id} → {provider.name}:{model}")

        text = provider.chat(system, user_prompt, timeout_sec=timeout_sec)
        try:
            return extract_json_object(text)
        except ProviderError:
            text = provider.chat(system, user_prompt + _JSON_FIX_SUFFIX, timeout_sec=timeout_sec)
            return extract_json_object(text)

    # ------------------------------------------------------------------
    # step handlers

    def _source_ingest(self, step_id: str, context: Context, tier: str, timeout: int) -> StepResult:
        workspace = context["workspace"]
        topic = context["topic"]
        mode = context.get("mode", "broad")
        round_num = int(context.get("round", 0))
        num_queries = int(context.get("num_queries") or 4)
        search_focus = context.get("search_focus") or ""

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        store = read_json_or(os.path.join(workspace, "evidence", "evidence_store.json"), [])
        existing_urls = {e.get("url") for e in store if isinstance(e, dict)}

        queries_resp = self._chat_json(
            step_id, "source-ingest.md", "ingest", tier,
            (
                f"Today: {today}\nDebate topic: {topic}\nMode: {mode}\nRound: {round_num}\n"
                f"Search focus (from the judge's last ruling, may be empty): {search_focus or '(none)'}\n\n"
                f"Generate {num_queries} diverse, high-signal web search queries for this topic. "
                f"Cover authoritative sources first. Respond as JSON: "
                f'{{"queries": ["query 1", "query 2", ...]}}'
            ),
            timeout,
        )
        queries = [q for q in queries_resp.get("queries", []) if isinstance(q, str)][: max(num_queries, 6)]

        results: list[dict] = []
        for query in queries:
            try:
                results.extend(self.search.search(query, max_results=5))
            except ProviderError as e:
                print(f"[{timestamp()}] search failed for {query!r}: {e}", flush=True)
        print(f"[{timestamp()}] source ingest collected {len(results)} raw results from {len(queries)} queries")

        if results:
            evidence_resp = self._chat_json(
                step_id, "source-ingest.md", "ingest", tier,
                (
                    f"Today: {today}\nDebate topic: {topic}\n\n"
                    f"Below are web search results. Select and structure every substantively "
                    f"relevant result into EvidenceItem objects following the data contract.\n"
                    f"Rules:\n"
                    f"- Do NOT invent items that are not backed by a provided result; do NOT fabricate URLs or quotes.\n"
                    f"- Skip duplicates of already-known URLs: {sorted(u for u in existing_urls if u)[:20]}\n"
                    f"- snippet must be a relevant verbatim excerpt from the result.\n"
                    f"- source_type ∈ web|twitter|academic|government|other; credibility_tier ∈ "
                    f"{sorted(_EVIDENCE_ALLOWED_TIERS)}; evidence_track ∈ {sorted(_EVIDENCE_ALLOWED_TRACKS)}; "
                    f"freshness_status ∈ {sorted(_EVIDENCE_ALLOWED_FRESHNESS)} (use 'timeless' for "
                    f"mechanism/trend/history evidence).\n"
                    f"- For twitter items set social_credibility_flag ∈ likely_reliable|needs_verification|"
                    f"likely_unreliable and verification_priority accordingly; otherwise null/low.\n\n"
                    f"Search results:\n{json.dumps(results, ensure_ascii=False, indent=1)}\n\n"
                    f'Respond as JSON: {{"evidence": [ EvidenceItem, ... ]}}'
                ),
                timeout,
            )

            known = {(e.get("url", ""), e.get("hash", "")) for e in store}
            added = 0
            for item in evidence_resp.get("evidence", []):
                if not isinstance(item, dict) or not item.get("snippet"):
                    continue
                snippet_hash = _snippet_hash(item.get("snippet", ""))
                url = item.get("url", "")
                if (url, snippet_hash) in known:
                    continue
                entry = {
                    "evidence_id": f"evi_{snippet_hash[:8]}",
                    "source_type": item.get("source_type") or "web",
                    "url": url,
                    "publisher": item.get("publisher") or "",
                    "published_at": item.get("published_at") or None,
                    "retrieved_at": _now_iso(),
                    "snippet": item.get("snippet", ""),
                    "hash": snippet_hash,
                    "credibility_tier": item.get("credibility_tier") if item.get("credibility_tier") in _EVIDENCE_ALLOWED_TIERS else "tier3_general",
                    "freshness_status": item.get("freshness_status") if item.get("freshness_status") in _EVIDENCE_ALLOWED_FRESHNESS else "current",
                    "evidence_track": item.get("evidence_track") if item.get("evidence_track") in _EVIDENCE_ALLOWED_TRACKS else "fact",
                    "social_credibility_flag": item.get("social_credibility_flag"),
                    "verification_priority": item.get("verification_priority") or "low",
                    "corroboration_status": item.get("corroboration_status"),
                    "discovered_by": "orchestrator",
                    "discovered_at_round": round_num,
                    "search_context": "initial_broad" if round_num == 0 else f"judge_feedback_round_{round_num}",
                }
                store.append(entry)
                known.add((url, snippet_hash))
                added += 1
            if added:
                write_json(os.path.join(workspace, "evidence", "evidence_store.json"), store)
            print(f"[{timestamp()}] source ingest added {added} evidence items")

        return StepResult(step_id=step_id, success=True, exit_code=0)

    def _freshness_check(self, step_id: str, context: Context, tier: str, timeout: int) -> StepResult:
        workspace = context["workspace"]
        store_path = os.path.join(workspace, "evidence", "evidence_store.json")
        store = read_json_or(store_path, [])
        if not store:
            return StepResult(step_id=step_id, success=True, exit_code=0)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resp = self._chat_json(
            step_id, "freshness-check.md", "ingest", tier,
            (
                f"Today: {today}\n\n"
                f"Review every evidence item's freshness_status. Fact-track items whose "
                f"published date is too old to support current-state claims become 'stale'. "
                f"Reasoning/mechanism/trend evidence is NEVER downgraded (stays 'timeless' or its "
                f"original status). Do not change anything else.\n\n"
                f"Evidence items:\n{json.dumps(_evidence_context(store), ensure_ascii=False, indent=1)}\n\n"
                f'Respond as JSON: {{"updates": [{{"evidence_id": "...", "freshness_status": "current|stale|timeless"}}, ...]}}\n'
                f"Include only items whose status actually changes."
            ),
            timeout,
        )

        by_id = {e.get("evidence_id"): e for e in store if isinstance(e, dict)}
        changed = 0
        for update in resp.get("updates", []):
            item = by_id.get(update.get("evidence_id"))
            new_status = update.get("freshness_status")
            if item and new_status in _EVIDENCE_ALLOWED_FRESHNESS and item.get("freshness_status") != new_status:
                item["freshness_status"] = new_status
                changed += 1
        if changed:
            write_json(store_path, store)
        print(f"[{timestamp()}] freshness check updated {changed} items")
        return StepResult(step_id=step_id, success=True, exit_code=0)

    def _debate_turn(self, step_id: str, context: Context, tier: str, timeout: int) -> StepResult:
        workspace = context["workspace"]
        side = context.get("side") or ("pro" if "_pro_" in step_id else "con")
        round_num = int(context.get("round", 1))
        fix_note = ""
        if context.get("fix_validation"):
            fix_note = ("\nYour previous output failed schema validation. Regenerate the turn "
                        "strictly matching the JSON contract; every argument must contain a "
                        "complete reasoning_chain with all five keys.\n")

        sections = [
            f"Today: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"Debate topic: {context.get('topic', '')}",
            f"Your side: {side}",
            f"Round: {round_num}",
            f"Mode: {context.get('mode', 'balanced')} | Speculation level: "
            f"{context.get('speculation', 'moderate')} | Depth: {context.get('depth', 'standard')}",
            fix_note,
            "\n=== Evidence store (citable; cite by evidence_id) ===",
            json.dumps(_evidence_context(read_json_or(os.path.join(workspace, "evidence", "evidence_store.json"), [])), ensure_ascii=False, indent=1),
            "\n=== Claim ledger so far ===",
            json.dumps(read_json_or(os.path.join(workspace, "claims", "claim_ledger.json"), []), ensure_ascii=False, indent=1),
        ]

        if round_num > 1:
            prev_dir = os.path.join(workspace, "rounds", f"round_{round_num - 1}")
            sections.append(f"\n=== Round {round_num - 1} artifacts (opponent turn and judge ruling) ===")
            for name in ("pro_turn.json", "con_turn.json", "judge_ruling.json"):
                sections.append(f"--- {name} ---")
                sections.append(json.dumps(read_json_or(os.path.join(prev_dir, name), {}), ensure_ascii=False)[:8000])

        sections.append(
            "\nOutput contract (JSON only):\n"
            '{"round": <int>, "side": "pro|con", '
            '"arguments": [{"claim_text": str, "claim_type": "fact|inference|analogy", '
            '"evidence_ids": [..], "reasoning_chain": {"observed_facts": str, "mechanism": str, '
            '"scenario_implication": str, "trigger_conditions": str, "falsification_conditions": str}}], '
            '"rebuttals": [{"target_claim_id": str, "rebuttal_text": str, "evidence_ids": [..]}], '
            '"mandatory_responses": [{"point_id": str, "response_text": str}], '
            '"new_evidence": [], '
            '"historical_wisdom": {"weight": "advisory", "references": [...]}, '
            '"speculative_scenarios": {"weight": "exploratory", "scenarios": [...]}}\n'
            "Cite ONLY evidence_ids present in the evidence store; centralised ingest keeps "
            "new_evidence empty. Argument claim_ids follow clm_<round>_<side>_<n>."
        )

        turn = self._chat_json(step_id, "debate-turn.md", side, tier, "\n".join(sections), timeout)
        turn.setdefault("round", round_num)
        turn["side"] = side
        turn.setdefault("new_evidence", [])

        out_path = os.path.join(workspace, "rounds", f"round_{round_num}", f"{side}_turn.json")
        write_json(out_path, turn)
        print(f"[{timestamp()}] wrote {side} turn for round {round_num}")
        return StepResult(step_id=step_id, success=True, exit_code=0)

    def _judge_audit(self, step_id: str, context: Context, tier: str, timeout: int) -> StepResult:
        workspace = context["workspace"]
        round_num = int(context.get("round", 1))
        round_dir = os.path.join(workspace, "rounds", f"round_{round_num}")

        sections = [
            f"Today: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"Round to audit: {round_num}",
            "\n=== Pro turn ===",
            json.dumps(read_json_or(os.path.join(round_dir, "pro_turn.json"), {}), ensure_ascii=False)[:9000],
            "\n=== Con turn ===",
            json.dumps(read_json_or(os.path.join(round_dir, "con_turn.json"), {}), ensure_ascii=False)[:9000],
            "\n=== Evidence store (independent verification basis) ===",
            json.dumps(_evidence_context(read_json_or(os.path.join(workspace, "evidence", "evidence_store.json"), [])), ensure_ascii=False, indent=1),
            "\n=== Claim ledger ===",
            json.dumps(read_json_or(os.path.join(workspace, "claims", "claim_ledger.json"), []), ensure_ascii=False, indent=1),
            "\nOutput contract (JSON only):\n"
            '{"round": <int>, '
            '"verification_results": [{"claim_id": str, "original_status": str, "new_status": '
            '"verified|contested|unverified|stale", "reasoning": str}], '
            '"causal_validity_flags": [{"claim_id": str, "issue": str, "severity": "critical|moderate|minor"}], '
            '"mandatory_response_points": [{"point_id": "mrp_<round>_<n>", "target": "pro|con|both", '
            '"point": str, "reason": str}], '
            '"historical_wisdom_assessment": [{"side": str, "historical_event": str, '
            '"relevance_grade": str, "honesty_grade": str, "note": str}], '
            '"round_summary": str}\n'
            "Every claim in both turns must appear in verification_results with claim_id "
            "clm_<round>_<side>_<n> and a non-empty reasoning. Verify claims against the evidence "
            "store yourself; never trust a debater's citation blindly.",
        ]

        ruling = self._chat_json(step_id, "judge-audit.md", "judge", tier, "\n".join(sections), timeout)
        ruling.setdefault("round", round_num)

        write_json(os.path.join(round_dir, "judge_ruling.json"), ruling)
        print(f"[{timestamp()}] wrote judge ruling for round {round_num}")
        return StepResult(step_id=step_id, success=True, exit_code=0)

    def _claim_ledger_update(self, step_id: str, context: Context, tier: str, timeout: int) -> StepResult:
        workspace = context["workspace"]
        round_num = int(context.get("round", 1))
        ledger_path = os.path.join(workspace, "claims", "claim_ledger.json")
        ledger = read_json_or(ledger_path, [])

        round_dir = os.path.join(workspace, "rounds", f"round_{round_num}")
        resp = self._chat_json(
            step_id, "claim-ledger-update.md", "ingest", tier,
            (
                f"Round: {round_num}\n\n"
                f"=== Existing claim ledger ===\n"
                f"{json.dumps(ledger, ensure_ascii=False, indent=1)}\n\n"
                f"=== This round's judge ruling ===\n"
                f"{json.dumps(read_json_or(os.path.join(round_dir, 'judge_ruling.json'), {}), ensure_ascii=False)[:9000]}\n\n"
                f"=== This round's turns (for any claims the judge identified but the ledger lacks) ===\n"
                f"pro: {json.dumps(read_json_or(os.path.join(round_dir, 'pro_turn.json'), {}), ensure_ascii=False)[:4000]}\n"
                f"con: {json.dumps(read_json_or(os.path.join(round_dir, 'con_turn.json'), {}), ensure_ascii=False)[:4000]}\n\n"
                f"Produce ledger updates reflecting the judge's verification_results: apply the new "
                f"statuses (with judge_note and last_verified_at from the ruling), and add any "
                f"missing claims as full ClaimItems (claim_id clm_<round>_<side>_<n>, round, speaker, "
                f"claim_type, claim_text, evidence_ids, status, mandatory_response flag).\n"
                f'Respond as JSON: {{"updates": [ ClaimItem, ... ]}}'
            ),
            timeout,
        )

        index = {item.get("claim_id"): item for item in ledger if isinstance(item, dict)}
        now = _now_iso()
        applied = 0
        for update in resp.get("updates", []):
            if not isinstance(update, dict) or not update.get("claim_id"):
                continue
            existing = index.get(update["claim_id"])
            if existing:
                for key in ("status", "judge_note", "mandatory_response", "conflict_details"):
                    if key in update and update[key] is not None:
                        existing[key] = update[key]
                existing["last_verified_at"] = now
            else:
                entry = {
                    "claim_id": update["claim_id"],
                    "round": update.get("round", round_num),
                    "speaker": update.get("speaker"),
                    "claim_type": update.get("claim_type", "fact"),
                    "claim_text": update.get("claim_text", ""),
                    "evidence_ids": update.get("evidence_ids", []),
                    "status": update.get("status", "unverified"),
                    "last_verified_at": now,
                    "judge_note": update.get("judge_note", ""),
                    "mandatory_response": bool(update.get("mandatory_response", False)),
                }
                ledger.append(entry)
                index[entry["claim_id"]] = entry
            applied += 1
        if applied:
            write_json(ledger_path, ledger)
        print(f"[{timestamp()}] claim ledger updated with {applied} entries")
        return StepResult(step_id=step_id, success=True, exit_code=0)

    def _final_synthesis(self, step_id: str, context: Context, tier: str, timeout: int) -> StepResult:
        workspace = context["workspace"]
        rounds_total = int(context.get("rounds", 0))
        rounds_dir = os.path.join(workspace, "rounds")

        rounds_payload: dict[str, Any] = {}
        for i in range(1, rounds_total + 1):
            rdir = os.path.join(rounds_dir, f"round_{i}")
            rounds_payload[f"round_{i}"] = {
                "pro_turn": read_json_or(os.path.join(rdir, "pro_turn.json"), {}),
                "con_turn": read_json_or(os.path.join(rdir, "con_turn.json"), {}),
                "judge_ruling": read_json_or(os.path.join(rdir, "judge_ruling.json"), {}),
            }

        sections = [
            f"Today: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"Debate topic: {context.get('topic', '')}",
            f"Total rounds: {rounds_total}",
            "\n=== All rounds ===",
            json.dumps(rounds_payload, ensure_ascii=False)[:45000],
            "\n=== Final claim ledger ===",
            json.dumps(read_json_or(os.path.join(workspace, "claims", "claim_ledger.json"), []), ensure_ascii=False, indent=1),
            "\n=== Evidence store ===",
            json.dumps(_evidence_context(read_json_or(os.path.join(workspace, "evidence", "evidence_store.json"), []), snippet_limit=200), ensure_ascii=False, indent=1),
            "\nOutput contract — a FinalReport JSON object with AT LEAST these keys:\n"
            '{"topic", "total_rounds", "generated_at", "verdict_summary", "report_path": '
            '"reports/debate_report.md", "verified_facts": [..], "probable_conclusions": [..], '
            '"contested_points": [{"point", "claim_ids": [..], "pro_position", "con_position", '
            '"key_rebuttals": [{"from", "target", "argument", "evidence_ids"}], "judge_assessment", '
            '"resolution_status": "unresolved|leaning_pro|leaning_con|partially_resolved"}], '
            '"to_verify": [..], '
            '"scenario_outlook": {"base_case", "upside_triggers", "downside_triggers", "falsification_conditions"}, '
            '"watchlist_24h": [{"item", "reversal_trigger", "monitoring_source"}]}\n'
            "Base every statement on the record; ground verified_facts in cross-confirmed claims; "
            "list genuinely contested points with the judge's assessment.",
        ]

        report = self._chat_json(step_id, "final-synthesis.md", "synthesis", tier, "\n".join(sections), timeout)
        report.setdefault("topic", context.get("topic", ""))
        report.setdefault("total_rounds", rounds_total)
        report.setdefault("generated_at", _now_iso())
        report.setdefault("report_path", "reports/debate_report.md")

        write_json(os.path.join(workspace, "reports", "final_report.json"), report)
        print(f"[{timestamp()}] wrote final_report.json")

        # Deterministic bilingual report rendering (v2 fallback renderer).
        from ..synthesis.fallback import run_renderer

        render = run_renderer(workspace)
        if not render.success:
            return StepResult(step_id=step_id, success=False,
                              error_type=render.error_type or "renderer_failed",
                              reason=render.reason, exit_code=render.exit_code)
        print(f"[{timestamp()}] rendered debate_report.md")
        return StepResult(step_id=step_id, success=True, exit_code=0)


def _workspace_from_prompt(prompt: str) -> str:
    for marker in ("Workspace: ", "workspace="):
        if marker in prompt:
            return prompt.rsplit(marker, 1)[1].strip()
    raise ValueError(f"No workspace in prompt: {prompt[:120]}")
