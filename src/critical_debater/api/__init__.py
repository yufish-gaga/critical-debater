"""API layer (v3 Phase 6): FastAPI backend serving debate state + live WebSocket feed.

Run with::

    uvicorn critical_debater.api.app:create_app --factory
    # or: python -m critical_debater.api <workspace>
"""

from .app import create_app
from .service import DebateService, DebateRun

__all__ = ["create_app", "DebateService", "DebateRun"]
