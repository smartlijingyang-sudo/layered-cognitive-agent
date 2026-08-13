"""Build computer use observations for journal + LobeHub wire."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_EXECUTION
from lca.contracts.models.core.decision import Observation
from lca.layer0_infra.computer.runtime import ComputerOpResult
from lca.layer0_infra.file_store import FileStore, persist_generated_files
from lca.layer0_infra.text.truncate import ASCII_ELLIPSIS, truncate_text
from lca.layer0_infra.workspace.deliverable import (
    publishable_file_parts,
    visible_generated_files,
)
from lca.layer0_infra.workspace.scope import get_run_workspace

_COMPUTER_TRUNCATE_LIMIT = 8000


def build_computer_observation(
    result: ComputerOpResult,
    *,
    tool_name: str,
    start: float,
    store: FileStore,
) -> Observation:
    """Build an Observation from a ComputerOpResult, storing generated files."""
    latency_ms = int((time.monotonic() - start) * 1000)
    plugin_state = dict(result.state)
    payload: dict[str, Any] = {
        "state": plugin_state,
        "content": result.content,
        "summary": _truncate(result.content),
    }
    if result.exec_result is not None:
        payload["exit_code"] = result.exec_result.exit_code
        plugin_state.setdefault("exitCode", result.exec_result.exit_code)

    command = str(plugin_state.get("command") or "")
    stdout = str(plugin_state.get("stdout") or result.content or "")
    # One put: reuse runtime-stored canonical parts, else persist generated_files.
    file_parts = publishable_file_parts(
        _reuse_or_persist_files(result, store, tool_name=tool_name),
        stdout=stdout,
        tool_name=tool_name,
        command=command,
    )
    plugin_state["files"] = file_parts

    extra: dict[str, Any] = {}
    if file_parts:
        extra["files"] = file_parts
        _record_harvest(file_parts, result=result, tool_name=tool_name)
    else:
        plugin_state.pop("files", None)

    if not result.success:
        extra[FAILURE_KIND] = FAILURE_KIND_EXECUTION
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=payload,
            content_type=ContentType.STRUCTURED,
            error=result.error or result.content or "computer operation failed",
            latency_ms=latency_ms,
            extra=extra,
        )

    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload=payload,
        content_type=ContentType.STRUCTURED,
        latency_ms=latency_ms,
        extra=extra,
    )


def _record_harvest(
    file_parts: list[dict[str, Any]],
    *,
    result: ComputerOpResult,
    tool_name: str,
) -> None:
    workspace = get_run_workspace()
    if workspace is None:
        return
    state = result.state if isinstance(result.state, dict) else {}
    stdout = str(state.get("stdout") or result.content or "")
    workspace.artifacts.record_harvest(
        file_parts,
        stdout=stdout,
        tool_name=tool_name,
        command=str(state.get("command") or ""),
    )


def _reuse_or_persist_files(
    result: ComputerOpResult,
    store: FileStore,
    *,
    tool_name: str,
) -> list[dict[str, Any]]:
    existing = result.state.get("files") if isinstance(result.state, dict) else None
    if isinstance(existing, list) and existing:
        return [part for part in existing if isinstance(part, dict) and part.get("name")]
    if result.generated_files:
        command = str(result.state.get("command") or "") if isinstance(result.state, dict) else ""
        return persist_generated_files(
            store,
            visible_generated_files(
                result.generated_files,
                tool_name=tool_name,
                command=command,
            ),
        )
    return []


def _truncate(text: str, limit: int = _COMPUTER_TRUNCATE_LIMIT) -> str:
    return truncate_text(text, limit - len(ASCII_ELLIPSIS), suffix=ASCII_ELLIPSIS)
