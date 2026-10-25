"""Shared CLI helpers for beginner-friendly errors."""

from __future__ import annotations

import sys


def cli_exit(message: str, next_step: str, code: int = 1) -> None:
    """Print error/next to stderr and exit (does not return)."""
    print(f"error: {message}", file=sys.stderr)
    print(f"next: {next_step}", file=sys.stderr)
    raise SystemExit(code)
