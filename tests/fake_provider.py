"""Fakes for the Phase 2 API layer: provider, registry, search."""

from __future__ import annotations

import json

from fake_agent import ledger_for_ruling, valid_judge_ruling, valid_turn


class FakeProvider:
    """Scripted provider: pops one response per chat() call."""

    name = "fake"

    def __init__(self, role: str, script: list):
        self.role = role
        self.script = list(script)
        self.calls: list[tuple[str, str]] = []

    def chat(self, system: str, user: str, timeout_sec: int | None = None) -> str:
        self.calls.append((system[:60], user))
        if not self.script:
            raise AssertionError(f"no scripted response left for role {self.role}; last prompt: {user[:200]}")
        response = self.script.pop(0)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)


class FakeRegistry:
    """One FakeProvider per role, fed from per-role script queues."""

    default_provider = "fake"

    def __init__(self, scripts: dict[str, list]):
        self.scripts = scripts
        self.providers: dict[str, FakeProvider] = {}

    def resolve(self, role: str, tier: str = "balanced"):
        if role not in self.providers:
            self.providers[role] = FakeProvider(role, self.scripts.get(role, []))
        return self.providers[role], f"fake-{role}-{tier}"


class FakeSearch:
    """Returns canned results for every query; records the queries."""

    name = "fake"

    def __init__(self, results_per_query: int = 2):
        self.results_per_query = results_per_query
        self.queries: list[str] = []
        self.scoped_queries: list[tuple[str, list[str] | None]] = []

    def search(self, query: str, max_results: int = 5,
               include_domains: list[str] | None = None) -> list[dict]:
        self.queries.append(query)
        self.scoped_queries.append((query, include_domains))
        return [
            {
                "title": f"Result {i} for {query}",
                "url": f"https://example.com/{abs(hash(query)) % 100000}/{i}",
                "snippet": f"Authoritative snippet {i} about {query}",
                "published_date": "2026-08-01",
            }
            for i in range(self.results_per_query)
        ]


def search_result_payload(n_queries: int, items_per_call: int) -> dict:
    return {
        "evidence": [
            {
                "url": f"https://example.com/evidence-batch-{n_queries}-{i}",
                "publisher": "Example News",
                "snippet": f"Structured evidence snippet {i} from batch {n_queries}",
                "source_type": "web",
                "credibility_tier": "tier2_reputable",
                "freshness_status": "current",
                "evidence_track": "fact",
            }
            for i in range(items_per_call)
        ]
    }


def fresh_queries() -> dict:
    return {"queries": ["topic economics 2026", "topic policy analysis"]}


def debate_turn_response(round_num: int, side: str) -> dict:
    return valid_turn(round_num, side)


def judge_response(round_num: int) -> dict:
    return valid_judge_ruling(round_num)


def ledger_response(round_num: int) -> dict:
    return {"updates": ledger_for_ruling(judge_response(round_num))}


def final_report_response(rounds: int) -> dict:
    return {
        "topic": "Test topic",
        "total_rounds": rounds,
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


def api_runner_scripts(rounds: int, evidence_batches: list[int]) -> dict[str, list]:
    """Script queues covering a full debate.

    Call order per the graph: round-0 ingest + freshness; per round
    (refresh ingest + freshness for round > 1), debate turns, judge, ledger;
    final synthesis. The ingest role serves source-ingest, freshness and
    claim-ledger steps, so its queue must follow that exact sequence.
    """
    scripts: dict[str, list] = {"ingest": [], "pro": [], "con": [], "judge": [], "synthesis": []}

    def batch(batch_id: int, count: int) -> list:
        return [fresh_queries(), search_result_payload(batch_id, count), {"updates": []}]

    scripts["ingest"].extend(batch(0, evidence_batches[0]))
    for round_num in range(1, rounds + 1):
        if round_num > 1:
            refresh_idx = round_num - 1
            count = evidence_batches[refresh_idx] if refresh_idx < len(evidence_batches) else 1
            scripts["ingest"].extend(batch(refresh_idx, count))
        scripts["pro"].append(debate_turn_response(round_num, "pro"))
        scripts["con"].append(debate_turn_response(round_num, "con"))
        scripts["judge"].append(judge_response(round_num))
        scripts["ingest"].append(ledger_response(round_num))
    scripts["synthesis"].append(final_report_response(rounds))
    return scripts
