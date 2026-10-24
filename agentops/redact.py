"""Optional redaction for sensitive ingest fields."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

MODES = frozenset({"off", "hash", "drop"})
STEP_TEXT_KEYS = ("input", "output", "traceback")


def resolve_mode(mode: str | None = None) -> str:
    raw = (mode if mode is not None else os.environ.get("AGENTOPS_REDACT", "off"))
    value = str(raw).strip().lower()
    if value not in MODES:
        raise ValueError(f"invalid redact mode: {raw!r}")
    return value


def _hash_text(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def redact_text(value: str | None, mode: str) -> tuple[str | None, int]:
    """Return (value, truncated_flag_reset). Non-text passthrough as drop/hash."""
    if mode == "off" or value is None:
        return value, -1  # -1 means caller keeps existing truncated flag
    if mode == "drop":
        return None, 0
    return _hash_text(value), 0


def redact_tags(tags: Any, mode: str) -> Any:
    if mode == "off" or tags is None:
        return tags
    data = tags
    if isinstance(tags, str):
        try:
            data = json.loads(tags)
        except json.JSONDecodeError:
            return tags
    if not isinstance(data, dict) or "end_user_id" not in data:
        return tags if isinstance(tags, str) else data
    out = dict(data)
    if mode == "drop":
        out.pop("end_user_id", None)
    else:
        out["end_user_id"] = _hash_text(str(data["end_user_id"]))
    return out


def apply_to_step(step: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode == "off":
        return step
    out = dict(step)
    for key in STEP_TEXT_KEYS:
        flag_key = f"{key}_truncated"
        new_val, flag = redact_text(out.get(key), mode)
        if flag >= 0:
            out[key] = new_val
            out[flag_key] = flag
    return out


def apply_to_run_fields(
    *,
    task_input: str | None,
    task_input_truncated: int,
    task_output: str | None,
    task_output_truncated: int,
    tags: Any,
    mode: str,
) -> dict[str, Any]:
    if mode == "off":
        return {
            "task_input": task_input,
            "task_input_truncated": task_input_truncated,
            "task_output": task_output,
            "task_output_truncated": task_output_truncated,
            "tags": tags,
        }
    tin, tin_f = redact_text(task_input, mode)
    tout, tout_f = redact_text(task_output, mode)
    return {
        "task_input": tin,
        "task_input_truncated": task_input_truncated if tin_f < 0 else tin_f,
        "task_output": tout,
        "task_output_truncated": task_output_truncated if tout_f < 0 else tout_f,
        "tags": redact_tags(tags, mode),
    }
