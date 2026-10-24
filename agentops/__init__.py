"""Lightweight Agent Operations (AgentOps / LLMOps) toolkit."""

from agentops.db import connect
from agentops.ingest import IngestError, ingest_run
from agentops.query import (
    get_run,
    list_runs,
    list_tool_failures,
    summarize_runs,
)

__version__ = "0.1.0"

__all__ = [
    "IngestError",
    "connect",
    "get_run",
    "ingest_run",
    "list_runs",
    "list_tool_failures",
    "summarize_runs",
    "__version__",
]
