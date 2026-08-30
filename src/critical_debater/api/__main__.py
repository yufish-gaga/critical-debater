"""Run the API server: ``python -m critical_debater.api [workspace]``.

With a workspace argument the server exposes that single debate workspace;
without one, debates are started via POST /api/debates.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    import uvicorn

    from .app import create_app

    if argv:
        workspace = argv[0]
        app = create_app(frontend_dist=None)
        # Pre-register the workspace as a debate so the UI can attach to it.
        service = app.state.service
        from .service import DebateRun

        import os

        service._runs["workspace"] = DebateRun(
            debate_id="workspace",
            workspace=workspace,
            topic=os.path.basename(workspace),
            rounds=0,
            status="attached",
        )
    else:
        app = create_app()

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
