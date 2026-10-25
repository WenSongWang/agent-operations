#!/usr/bin/env python3
"""CLI wrapper; prefer `agentops-smoke` after pip install."""

from agentops.smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
