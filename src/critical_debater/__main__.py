"""CLI entry point: ``python -m critical_debater <workspace> <config_or_topic> [rounds]``.

Mirrors the v2 orchestrator CLI surface (``debate_orchestrator_generic.py``).
"""

from __future__ import annotations

import os
import sys

from .config import DebateOptions
from .errors import DebateStepFailure
from .graph.runner import run_debate
from .workspace import init_workspace, timestamp


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv) if argv is None else list(argv)
    resume = "--resume" in argv
    argv = [a for a in argv if a != "--resume"]
    if len(argv) < 3:
        print(f"Usage: {argv[0]} <workspace_dir> <config_or_topic> [rounds] [--resume]")
        sys.exit(1)

    workspace = os.path.abspath(argv[1])
    config_or_topic = argv[2]
    rounds = int(argv[3]) if len(argv) > 3 else 3

    if os.path.isfile(config_or_topic):
        opts = DebateOptions.from_config(config_or_topic)
    else:
        opts = DebateOptions(topic=config_or_topic, rounds=rounds)
        # Initialize workspace with explicit DebateConfig defaults (resume
        # runs on an existing workspace keep their checkpoint untouched).
        if not os.path.exists(os.path.join(workspace, "config.json")):
            init_workspace(
                workspace,
                opts.topic,
                opts.rounds,
                depth=opts.depth,
                mode=opts.mode,
                evidence_refresh=opts.evidence_refresh,
                language=opts.language,
            )

    try:
        run_debate(workspace, opts, resume=resume)
    except DebateStepFailure as e:
        print(f"[{timestamp()}] Debate failed: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
