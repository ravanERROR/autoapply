"""Main entry point for JobApply bot orchestrator."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots.orchestrator import main

if __name__ == "__main__":
    args = list(sys.argv[1:])
    if not any(arg == "--platform" or arg.startswith("--platform=") for arg in args):
        args = ["--platform", "all", *args]
    raise SystemExit(main(args))
