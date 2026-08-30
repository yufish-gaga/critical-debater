"""Final synthesis support: deterministic fallback renderer + report backup (v3 Phase 1 port)."""

from .fallback import debate_report_path, final_report_path, report_backup_path, run_renderer

__all__ = ["debate_report_path", "final_report_path", "report_backup_path", "run_renderer"]
