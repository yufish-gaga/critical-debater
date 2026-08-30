"""Evidence system: deterministic store merging (v3 Phase 1 port)."""

from .merge import evidence_store_path, load_evidence_store, merge_new_evidence

__all__ = ["evidence_store_path", "load_evidence_store", "merge_new_evidence"]
