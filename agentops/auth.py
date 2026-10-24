"""API key auth and per-key project ACL."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AuthError(PermissionError):
    """Missing/invalid credentials or project not allowed."""


@dataclass(frozen=True)
class Principal:
    name: str
    projects: frozenset[str]

    def allows_project(self, project: str | None) -> bool:
        if "*" in self.projects:
            return True
        if project is None:
            return False
        return project in self.projects

    def require_project(self, project: str | None) -> None:
        if not self.allows_project(project):
            raise AuthError(f"project not allowed: {project!r}")


def load_api_keys(
    raw: str | None = None, path: str | Path | None = None
) -> dict[str, Principal]:
    """Load API keys from JSON object: {\"key\": {\"projects\": [\"demo\"]}}."""
    text = raw
    if text is None:
        text = os.environ.get("AGENTOPS_API_KEYS")
    file_path = path
    if file_path is None:
        env_path = os.environ.get("AGENTOPS_API_KEYS_PATH")
        file_path = env_path
    if (not text) and file_path:
        text = Path(file_path).read_text(encoding="utf-8")
    if not text:
        return {}

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("API keys JSON must be an object")

    keys: dict[str, Principal] = {}
    for key, meta in data.items():
        if not isinstance(key, str) or not key:
            raise ValueError("API key names must be non-empty strings")
        if isinstance(meta, list):
            projects = meta
            name = key[:8]
        elif isinstance(meta, dict):
            projects = meta.get("projects", ["*"])
            name = str(meta.get("name") or key[:8])
        else:
            raise ValueError(f"invalid API key entry for {key!r}")
        if not isinstance(projects, list) or not projects:
            raise ValueError(f"projects required for API key {key!r}")
        keys[key] = Principal(name=name, projects=frozenset(str(p) for p in projects))
    return keys


def extract_api_key(headers: Any) -> str | None:
    """Read Bearer token or X-API-Key from headers mapping."""
    auth = headers.get("Authorization") or headers.get("authorization")
    if auth:
        parts = str(auth).split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip() or None
    key = headers.get("X-API-Key") or headers.get("x-api-key")
    if key:
        return str(key).strip() or None
    return None


def authenticate(
    headers: Any, keys: dict[str, Principal] | None = None
) -> Principal | None:
    """Return Principal when keys are configured; None when auth is disabled."""
    table = keys if keys is not None else load_api_keys()
    if not table:
        return None
    token = extract_api_key(headers)
    if not token:
        raise AuthError("missing API key")
    principal = table.get(token)
    if principal is None:
        raise AuthError("invalid API key")
    return principal


def scope_project_filter(
    principal: Principal | None, project: str | None
) -> str | None:
    """Resolve project filter under ACL. May raise AuthError."""
    if principal is None:
        return project
    if "*" in principal.projects:
        return project
    if project is not None:
        principal.require_project(project)
        return project
    if len(principal.projects) == 1:
        return next(iter(principal.projects))
    raise AuthError("project query parameter required")
