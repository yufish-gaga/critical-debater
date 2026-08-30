"""Evidence system: store merging + Chinese source adaptation (v3 Phase 3)."""

from .merge import evidence_store_path, load_evidence_store, merge_new_evidence
from .chinese import (
    ChineseQueryOptimizer,
    ChineseSourceRegistry,
    QueryRequest,
    contains_cjk,
    detect_source_language,
    domain_of,
)

__all__ = [
    "evidence_store_path",
    "load_evidence_store",
    "merge_new_evidence",
    "ChineseSourceRegistry",
    "ChineseQueryOptimizer",
    "QueryRequest",
    "contains_cjk",
    "detect_source_language",
    "domain_of",
]
