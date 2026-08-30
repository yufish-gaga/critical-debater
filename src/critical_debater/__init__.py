"""Critical Debater v3 — LangGraph-orchestrated multi-agent adversarial debate system.

Phase 1 (core architecture migration):
- Orchestration moved from the custom loop in
  ``critical-debater-suite/scripts/debate_orchestrator_generic.py``
  to a LangGraph state graph (see :mod:`critical_debater.graph`).
- The 4-agent debate logic (Pro / Con / Judge capabilities dispatched through
  CLI runtimes) is preserved unchanged; the workspace layout and audit trail
  are byte-compatible with v2.
"""

__version__ = "3.0.0.phase1"
