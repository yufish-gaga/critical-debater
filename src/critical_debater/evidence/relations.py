"""Evidence relationship graph (v3 Phase 4, 证据关系图谱).

Builds a deterministic graph over the evidence store and claim ledger:

- evidence nodes (tier, language, credibility score when available)
- claim nodes (status, speaker)
- edges:
  - ``duplicate_of``   same url or same content hash
  - ``same_domain``    co-located on one registrable domain (cluster signal)
  - ``co_cited``       two evidence items cited by the same claim (weight =
                       number of shared claims)
  - ``supports``       claim → evidence citation
  - ``contradicts``    from judge ``conflict_details`` (source_a vs source_b)

No LLM calls; output persisted to ``evidence/evidence_graph.json``.
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from typing import Optional

from .chinese import domain_of
from .credibility import load_credibility_scores
from .merge import evidence_store_path
from ..workspace import read_json_or, timestamp, write_json

MAX_SAME_DOMAIN_EDGES_PER_NODE = 8


def _edge(src: str, dst: str, kind: str, **attrs) -> dict:
    edge = {"source": src, "target": dst, "kind": kind}
    edge.update(attrs)
    return edge


def build_evidence_graph(workspace: str,
                         scores: Optional[dict[str, float]] = None) -> dict:
    store = read_json_or(evidence_store_path(workspace), [])
    claims = read_json_or(os.path.join(workspace, "claims", "claim_ledger.json"), [])
    if scores is None:
        scores = load_credibility_scores(workspace)

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_evidence: set[str] = set()

    for item in store:
        if not isinstance(item, dict) or not item.get("evidence_id"):
            continue
        evidence_id = item["evidence_id"]
        seen_evidence.add(evidence_id)
        nodes.append({
            "id": evidence_id,
            "type": "evidence",
            "credibility_tier": item.get("credibility_tier"),
            "source_language": item.get("source_language"),
            "domain": domain_of(item.get("url") or ""),
            "credibility_score": scores.get(evidence_id),
        })

    claim_ids = set()
    for claim in claims:
        if not isinstance(claim, dict) or not claim.get("claim_id"):
            continue
        claim_id = claim["claim_id"]
        claim_ids.add(claim_id)
        nodes.append({
            "id": claim_id,
            "type": "claim",
            "status": claim.get("status"),
            "speaker": claim.get("speaker"),
            "round": claim.get("round"),
        })

    # --- evidence ↔ evidence edges -----------------------------------

    by_url: dict[str, list[str]] = defaultdict(list)
    by_hash: dict[str, list[str]] = defaultdict(list)
    by_domain: dict[str, list[str]] = defaultdict(list)
    for item in store:
        if not isinstance(item, dict) or not item.get("evidence_id"):
            continue
        evidence_id = item["evidence_id"]
        if item.get("url"):
            by_url[item["url"]].append(evidence_id)
        if item.get("hash"):
            by_hash[item["hash"]].append(evidence_id)
        host = domain_of(item.get("url") or "")
        if host:
            by_domain[host].append(evidence_id)

    seen_pairs: set[tuple[str, str, str]] = set()

    def add_pair(a: str, b: str, kind: str, **attrs) -> None:
        if a == b:
            return
        key = tuple(sorted((a, b))) + (kind,)
        if key in seen_pairs:
            return
        seen_pairs.add(key)
        edges.append(_edge(key[0], key[1], kind, **attrs))

    for group in list(by_url.values()) + list(by_hash.values()):
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                add_pair(group[i], group[j], "duplicate_of")

    for domain, group in by_domain.items():
        if len(group) < 2:
            continue
        # Link each item to at most MAX peers on the same domain to keep the
        # graph small on large stores.
        for i, evidence_id in enumerate(group):
            for other in group[i + 1:i + 1 + MAX_SAME_DOMAIN_EDGES_PER_NODE]:
                add_pair(evidence_id, other, "same_domain", domain=domain)

    # --- claim ↔ evidence edges ---------------------------------------

    co_citation: Counter = Counter()
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("claim_id") not in claim_ids:
            continue
        claim_id = claim["claim_id"]
        cited = [e for e in (claim.get("evidence_ids") or []) if e in seen_evidence]
        for evidence_id in cited:
            edges.append(_edge(claim_id, evidence_id, "supports"))
        for i, a in enumerate(cited):
            for b in cited[i + 1:]:
                pair = tuple(sorted((a, b)))
                co_citation[pair] += 1
    for (a, b), weight in co_citation.items():
        add_pair(a, b, "co_cited", weight=weight)

    # --- contradiction edges from judge conflict_details ---------------

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        for conflict in claim.get("conflict_details") or []:
            if not isinstance(conflict, dict):
                continue
            source_a = (conflict.get("source_a") or {}).get("evidence_id")
            source_b = (conflict.get("source_b") or {}).get("evidence_id")
            if source_a in seen_evidence and source_b in seen_evidence:
                add_pair(source_a, source_b, "contradicts",
                         divergence_point=conflict.get("divergence_point"))

    evidence_count = sum(1 for n in nodes if n["type"] == "evidence")
    domain_clusters = sum(1 for group in by_domain.values() if len(group) >= 2)
    corroborated = sum(1 for e in store if isinstance(e, dict) and e.get("corroboration_status") == "corroborated")

    return {
        "generated_at": timestamp(),
        "stats": {
            "evidence_nodes": evidence_count,
            "claim_nodes": len(claim_ids),
            "edges": len(edges),
            "domain_clusters": domain_clusters,
            "corroborated": corroborated,
        },
        "nodes": nodes,
        "edges": edges,
    }


def write_evidence_graph(workspace: str, scores: Optional[dict[str, float]] = None) -> dict:
    graph = build_evidence_graph(workspace, scores)
    write_json(os.path.join(workspace, "evidence", "evidence_graph.json"), graph)
    return graph
