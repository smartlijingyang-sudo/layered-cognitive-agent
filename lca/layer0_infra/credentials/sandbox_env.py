"""Sandbox credential injection — env vars for skill scripts (LobeHub creds parity)."""

from __future__ import annotations

import json

from lca.layer0_infra.search.settings import get_search_settings


def resolve_sandbox_env() -> dict[str, str]:
    """Resolve credentials to inject into Onlyboxes guest environment."""
    env: dict[str, str] = {}
    search = get_search_settings()
    tavily_key = (search.tavily_api_key or "").strip()
    if tavily_key:
        env["TAVILY_API_KEY"] = tavily_key
    return env


def build_sandbox_env_preamble(env: dict[str, str] | None = None) -> str:
    """Python preamble setting os.environ before user/skill code runs."""
    resolved = env if env is not None else resolve_sandbox_env()
    if not resolved:
        return ""
    literal = json.dumps(resolved, ensure_ascii=False)
    return f"""
import os as _lca_cred_os
for _lca_k, _lca_v in {literal}.items():
    _lca_cred_os.environ[_lca_k] = _lca_v
"""
