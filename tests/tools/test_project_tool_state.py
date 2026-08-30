"""Tests for the contract.project module.

Each test exercises one of the four public functions against a small,
pre-registered contract.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.observability.journal import ToolInvoked
from lca.infrastructure.tools.contract import (
    REGISTRY,
    FieldSpec,
    RenderContract,
    contract,
    project_args,
    project_content,
    project_full,
    project_tool_state,
)
from lca.infrastructure.tools.contract.project import _MISSING, _read_field

# ── fixtures ────────────────────────────────────────────────────────────────


@contract(
    RenderContract(
        tool_name="__tproj_test_a",
        identifier="test",
        api_name="testA",
        args=(
            FieldSpec("skill_id", "name", "string", "argument"),
            FieldSpec("timeout", "timeout", "int", "argument"),
        ),
        state=(
            FieldSpec("name", "name", "string", "observation"),
            FieldSpec("stdout", "stdout", "string", "observation"),
            FieldSpec("execution_env", "executionEnv", "string", "observation"),
        ),
        content_field="text",
    )
)
class _TestToolA:
    pass


@contract(
    RenderContract(
        tool_name="__tproj_test_b",
        identifier="test",
        api_name="testB",
        args=(FieldSpec("path", "path", "string", "argument"),),
        state=(
            FieldSpec("path", "path", "string", "observation"),
            FieldSpec("size", "size", "int", "observation").optional(),
            FieldSpec("file_type", "fileType", "string", "observation").optional(),
            FieldSpec("encoding", "encoding", "string", "observation").optional(),
        ),
        streaming=(FieldSpec("stdout", "stdout", "string", "observation"),),
    )
)
class _TestToolB:
    pass


@pytest.fixture(autouse=True)
def _snapshot_registry():
    saved = dict(REGISTRY)
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


def _obs(payload: dict[str, Any], success: bool = True) -> Observation:
    return Observation(
        observation_id="obs1",
        success=success,
        payload=payload,
        content_type="text",
        latency_ms=0,
    )


# ── project_args ────────────────────────────────────────────────────────────


def test_projects_argument_source_with_rename() -> None:
    """LCA 'skill_id' → LobeHub 'name' rename applied via wire_key."""
    out = project_args("__tproj_test_a", {"skill_id": "anthropic-pdf"})
    assert out == {"name": "anthropic-pdf"}


def test_omits_missing_args() -> None:
    out = project_args("__tproj_test_a", {"skill_id": "x"})
    # `timeout` not in args → omitted entirely (both required and optional missing)
    assert "timeout" not in out


def test_unknown_tool_returns_empty() -> None:
    assert project_args("__nonexistent_tool__", {"x": 1}) == {}


# ── project_tool_state ──────────────────────────────────────────────────────


def test_projects_observation_source_with_wire_key_camelcase() -> None:
    """wire_key transforms python_key 'execution_env' → 'executionEnv'."""
    obs = _obs({"name": "ok", "stdout": "hi", "execution_env": "sandbox"})
    out = project_tool_state("__tproj_test_a", {"skill_id": "x"}, obs)
    assert out == {"name": "ok", "stdout": "hi", "executionEnv": "sandbox"}


def test_required_missing_state_field_omitted() -> None:
    """Required field absent → omitted from state (no partial state)."""
    obs = _obs({"name": "ok", "stdout": "hi"})  # no execution_env
    out = project_tool_state("__tproj_test_a", {"skill_id": "x"}, obs)
    assert "executionEnv" not in out


def test_optional_missing_state_field_emits_none() -> None:
    """Optional field absent → emitted as None so frontend knows it exists."""
    obs = _obs({"path": "/var/data/x"})
    out = project_tool_state("__tproj_test_b", {"path": "/var/data/x"}, obs)
    assert out["path"] == "/var/data/x"
    assert out["size"] is None
    assert out["fileType"] is None
    assert out["encoding"] is None


def test_unknown_tool_returns_empty_state() -> None:
    obs = _obs({"anything": 1})
    assert project_tool_state("__nonexistent_tool__", {}, obs) == {}


def test_skips_evidence_ref_and_constant_sources() -> None:
    """Fields sourced from evidence_ref / constant are not read from args/obs."""

    @contract(
        RenderContract(
            tool_name="__tproj_skip_sources",
            identifier="test",
            api_name="skip",
            args=(),
            state=(
                FieldSpec("from_obs", "fromObs", "string", "observation"),
                FieldSpec("from_ref", "fromRef", "string", "evidence_ref"),
                FieldSpec("from_const", "fromConst", "string", "constant"),
            ),
        )
    )
    class _Skip:
        pass

    obs = _obs({"from_obs": "a", "from_ref": "b", "from_const": "c"})
    out = project_tool_state("__tproj_skip_sources", {}, obs)
    assert out == {"fromObs": "a"}


# ── project_content ─────────────────────────────────────────────────────────


def test_content_field_extracted() -> None:
    obs = _obs({"text": "hello world"})
    assert project_content("__tproj_test_a", obs) == "hello world"


def test_content_field_missing_returns_none() -> None:
    obs = _obs({"other": "x"})
    assert project_content("__tproj_test_a", obs) is None


def test_content_field_non_string_returns_none() -> None:
    obs = _obs({"text": 42})
    assert project_content("__tproj_test_a", obs) is None


# ── project_full ────────────────────────────────────────────────────────────


def test_full_returns_args_state_content() -> None:
    obs = _obs({"name": "ok", "stdout": "hi", "execution_env": "sandbox", "text": "body"})
    out = project_full("__tproj_test_a", {"skill_id": "x"}, obs)
    assert out == {
        "args": {"name": "x"},
        "state": {"name": "ok", "stdout": "hi", "executionEnv": "sandbox"},
        "content": "body",
    }


# ── internals ───────────────────────────────────────────────────────────────


def test_read_field_returns_missing_sentinel_for_unknown_source() -> None:
    f = FieldSpec("x", "x", "string", "constant")
    assert _read_field(f, {}, {}) is _MISSING


def test_read_field_argument_present() -> None:
    f = FieldSpec("a", "a", "string", "argument")
    assert _read_field(f, {"a": "v"}, {}) == "v"


def test_read_field_argument_absent() -> None:
    f = FieldSpec("a", "a", "string", "argument")
    assert _read_field(f, {}, {}) is _MISSING


def test_read_field_observation_present() -> None:
    f = FieldSpec("a", "a", "string", "observation")
    assert _read_field(f, {}, {"a": "v"}) == "v"


def test_read_field_observation_absent() -> None:
    f = FieldSpec("a", "a", "string", "observation")
    assert _read_field(f, {"a": "ignored"}, {}) is _MISSING


# ── ToolInvoked integration ─────────────────────────────────────────────────


def test_tool_invoked_accepts_projected_state_field() -> None:
    """ToolInvoked must accept `projected_state` as a constructor field."""
    ev = ToolInvoked(
        tool_name="executeCode",
        invocation_id="inv1",
        ok=True,
        latency_ms=10,
        projected_state={"stdout": "ok", "executionEnv": "sandbox"},
    )
    assert ev.projected_state == {"stdout": "ok", "executionEnv": "sandbox"}


def test_tool_invoked_default_projected_state_is_empty() -> None:
    ev = ToolInvoked(tool_name="x", invocation_id="y")
    assert ev.projected_state == {}


# ── real-shape regression: Computer + Skill observations must be flattened ──


def _real_computer_observation() -> Observation:
    """Mimic build_computer_observation output (post ADR-0102 flattening)."""
    return Observation(
        observation_id="obs1",
        success=True,
        payload={
            "stdout": "/mnt/data/x.xlsx\n",
            "stderr": "",
            "files": [],
            "command": "find / -name x",
            "description": "Find uploaded file location",
            "execution_env": "sandbox",
            "exit_code": 0,
            "content": "/mnt/data/x.xlsx\n",
            "summary": "/mnt/data/x.xlsx",
        },
    )


def _real_skill_observation() -> Observation:
    """Mimic SkillActivateTool.execute output (post ADR-0102 flattening)."""
    return Observation(
        observation_id="obs2",
        success=True,
        payload={
            "text": "<body>",
            "skill_id": "anthropics-skills-xlsx",
            "name": "anthropics-skills-xlsx",
            "title": "anthropics-skills-xlsx",
            "content": "<body>",
            "description": "summary text",
            "has_resources": False,
            "success": True,
            "source": "agent",
            "id": "anthropics-skills-xlsx",
            "resources": [],
        },
    )


def test_run_command_projects_real_computer_observation() -> None:
    """``runCommand`` contract reads snake_case fields from the top-level
    payload. The legacy ``"state"`` sub-dict is gone; flatten happened at
    observation construction (lca_computer/observations.py)."""
    proj = project_tool_state(
        "runCommand",
        {"command": "find / -name x", "description": "Find"},
        _real_computer_observation(),
    )
    assert proj == {
        "stdout": "/mnt/data/x.xlsx\n",
        "stderr": "",
        "files": [],
        "exitCode": 0,
        "executionEnv": "sandbox",
    }


def test_activate_skill_projects_real_skill_observation() -> None:
    """``activate_skill`` contract reads ``has_resources`` (snake_case) at
    the top level. The legacy ``"state"`` sub-dict is gone; flattening
    happens at construction (skills/activate_tool.py)."""
    proj = project_tool_state(
        "activate_skill",
        {"skill_id": "anthropics-skills-xlsx"},
        _real_skill_observation(),
    )
    assert proj == {
        "name": "anthropics-skills-xlsx",
        "title": "anthropics-skills-xlsx",
        "hasResources": False,
        "content": "<body>",
    }


def test_computer_observation_payload_is_flattened() -> None:
    """Verify build_computer_observation no longer emits the legacy
    ``"state"`` sub-dict and snake_cases renderer-facing fields."""
    import os
    import tempfile
    from pathlib import Path

    from lca.contracts.models.core.sandbox import SandboxExecResult
    from lca.infrastructure.computer.op_result import ComputerOpResult
    from lca.infrastructure.file_store import LocalFileStore
    from lca.infrastructure.tools.lca_computer.observations import build_computer_observation

    with tempfile.TemporaryDirectory() as tmp:
        store = LocalFileStore(root=Path(os.path.join(tmp, "files")))
        result = ComputerOpResult(
            success=True,
            content="ok\n",
            exec_result=SandboxExecResult(exit_code=0, stdout="ok\n", stderr=""),
            state={
                "command": "true",
                "execution_env": "sandbox",
                "stdout": "ok\n",
                "stderr": "",
            },
            generated_files=(),
        )
        obs = build_computer_observation(result, tool_name="runCommand", start=0.0, store=store)
    assert "state" not in obs.payload
    assert obs.payload["execution_env"] == "sandbox"
    assert obs.payload["exit_code"] == 0
    assert obs.payload["stdout"] == "ok\n"


def test_skill_activate_observation_payload_is_flattened() -> None:
    """SkillActivateTool.execute flattens its renderer state into the
    top-level payload (no nested ``"state"`` key)."""
    import asyncio
    import tempfile
    from pathlib import Path

    from lca.infrastructure.skills.disk_store import DiskSkillPackageStore
    from lca.infrastructure.skills.settings import SkillSettings
    from lca.infrastructure.tools.skills.activate_tool import SkillActivateTool

    with tempfile.TemporaryDirectory() as tmp:
        settings = SkillSettings(cache_dir=Path(tmp))
        store = DiskSkillPackageStore(settings)
        store.install_package(
            skill_id="demo",
            skill_md_text="---\nname: demo\ndescription: d\n---\nDo work",
            resource_files={"tips.md": b"tip"},
            source_url="u",
        )
        obs = asyncio.run(SkillActivateTool(store).execute({"skill_id": "demo"}))
    assert obs.success
    assert "state" not in obs.payload
    assert obs.payload["has_resources"] is True
    assert obs.payload["name"] == "demo"
    assert obs.payload["title"] == "demo"
    assert obs.payload["description"] == "d"


# ── per-tool contract coverage ───────────────────────────────────────
# ADR-0102: each sandbox tool's contract python_key MUST match the keys
# the runtime puts in observation.payload.  These tests pin down that
# invariant for all 13 computer tools + 5 skill tools + search.


def _fixture_observe(tool_name: str, payload: dict) -> dict[str, Any]:
    """Run ``project_tool_state`` and return the projected dict."""
    from lca.contracts.models.core.decision import Observation

    obs = Observation(
        observation_id=f"obs-{tool_name}",
        success=True,
        payload=payload,
    )
    return project_tool_state(tool_name, {}, obs)


@pytest.mark.parametrize(
    ("tool_name", "payload", "expected_wire"),
    [
        # ── cloud sandbox ──
        (
            "executeCode",
            {
                "stdout": "hello\n",
                "stderr": "",
                "files": [],
                "exit_code": 0,
                "execution_env": "sandbox",
                "language": "python",
            },
            {
                "stdout": "hello\n",
                "stderr": "",
                "files": [],
                "exitCode": 0,
                "executionEnv": "sandbox",
            },
        ),
        (
            "runCommand",
            {
                "command": "ls",
                "description": "list",
                "stdout": "a\n",
                "stderr": "",
                "files": [],
                "exit_code": 0,
                "execution_env": "sandbox",
            },
            {
                "stdout": "a\n",
                "stderr": "",
                "files": [],
                "exitCode": 0,
                "executionEnv": "sandbox",
            },
        ),
        (
            "listFiles",
            {
                "files": [{"name": "x", "path": "/x", "isDirectory": False, "size": 10}],
                "total_count": 1,
                "directory_path": "/scratch",
            },
            {
                "files": [{"name": "x", "path": "/x", "isDirectory": False, "size": 10}],
                "totalCount": 1,
                "directoryPath": "/scratch",
            },
        ),
        (
            "readFile",
            {
                "path": "/x.txt",
                "content": "data",
                "filename": "x.txt",
                "file_type": "text",
            },
            {
                "path": "/x.txt",
                "content": "data",
                "filename": "x.txt",
                "fileType": "text",
                # optional-but-missing → None per ADR-0102 §4.1 rule 3
                "startLine": None,
                "endLine": None,
                "totalLines": None,
                "charCount": None,
            },
        ),
        (
            "writeFile",
            {"path": "/x.txt", "bytes_written": 12},
            {"path": "/x.txt", "bytesWritten": 12},
        ),
        (
            "editFile",
            {"path": "/x.txt", "replacements": 3, "lines_added": 2, "lines_deleted": 1},
            {"path": "/x.txt", "replacements": 3, "linesAdded": 2, "linesDeleted": 1},
        ),
        (
            "searchFiles",
            {
                "results": [{"name": "x", "path": "/x", "isDirectory": False, "size": 10}],
                "total_count": 1,
            },
            {
                "results": [{"name": "x", "path": "/x", "isDirectory": False, "size": 10}],
                "totalCount": 1,
            },
        ),
        (
            "moveFiles",
            {
                "results": [{"source": "/a", "destination": "/b", "success": True}],
                "success_count": 1,
                "total_count": 1,
            },
            {
                "results": [{"source": "/a", "destination": "/b", "success": True}],
                "successCount": 1,
                "totalCount": 1,
            },
        ),
        (
            "grepContent",
            {
                "matches": [{"path": "/x", "line": 5, "content": "needle"}],
                "total_matches": 1,
                "pattern": "needle",
            },
            {
                "matches": [{"path": "/x", "line": 5, "content": "needle"}],
                "totalMatches": 1,
                "pattern": "needle",
            },
        ),
        (
            "globFiles",
            {
                "files": [{"name": "x", "path": "/x", "size": 10}],
                "total_count": 1,
                "pattern": "*.txt",
            },
            {
                "files": [{"name": "x", "path": "/x", "size": 10}],
                "totalCount": 1,
                "pattern": "*.txt",
            },
        ),
        (
            "getCommandOutput",
            {
                "stdout": "partial\n",
                "stderr": "",
                "files": [],
                "exit_code": 0,
                "command_id": "abc",
                "running": False,
                "partial": False,
            },
            {
                "stdout": "partial\n",
                "stderr": "",
                "files": [],
                "exitCode": 0,
                "commandId": "abc",
                "running": False,
                "partial": False,
            },
        ),
        (
            "killCommand",
            {"command_id": "abc", "killed": True},
            {"commandId": "abc", "killed": True},
        ),
        (
            "exportFile",
            {
                "path": "/x.bin",
                "filename": "x.bin",
                "mime_type": "application/octet-stream",
                "size": 100,
                "download_url": "/files/x.bin",
            },
            {
                "path": "/x.bin",
                "filename": "x.bin",
                "mimeType": "application/octet-stream",
                "size": 100,
                "downloadUrl": "/files/x.bin",
            },
        ),
        # ── error annotations on shell tools ──
        (
            "executeCode",
            {
                "stdout": "",
                "stderr": "NameError: x",
                "files": [],
                "exit_code": 1,
                "execution_env": "sandbox",
                "error_summary": "NameError: x",
                "error_kind": "execution",
            },
            {
                "stdout": "",
                "stderr": "NameError: x",
                "files": [],
                "exitCode": 1,
                "executionEnv": "sandbox",
                "errorSummary": "NameError: x",
                "errorKind": "execution",
            },
        ),
    ],
)
def test_per_tool_projection(tool_name: str, payload: dict, expected_wire: dict) -> None:
    """Each sandbox tool's contract reads the python_keys the runtime
    emits and produces the camelCase wire_keys LobeHub expects."""
    assert _fixture_observe(tool_name, payload) == expected_wire


def test_legacy_camelcase_payload_gets_normalised() -> None:
    """``_normalize_guest_state`` bridges the on-guest camelCase renderer
    keys to the snake_case python keys the contracts declare.  Any tool
    that forgets to call it would leak camelCase into observation.payload
    and the projection would lose fields; this test pins the rename table.
    """
    from lca.infrastructure.computer.runtime_exec import _normalize_guest_state

    state = {
        "success": True,
        "stdout": "x",
        "stderr": "",
        "exitCode": 0,
        "executionEnv": "sandbox",
        "commandId": "abc",
        "totalCount": 5,
        "directoryPath": "/d",
        "fileType": "text",
        "mimeType": "text/plain",
        "bytesWritten": 12,
        "createDirectories": True,
        "isBackground": False,
        "output": "x",  # alias — should be dropped
    }
    _normalize_guest_state(state)
    assert state["exit_code"] == 0
    assert state["execution_env"] == "sandbox"
    assert state["command_id"] == "abc"
    assert state["total_count"] == 5
    assert state["directory_path"] == "/d"
    assert state["file_type"] == "text"
    assert state["mime_type"] == "text/plain"
    assert state["bytes_written"] == 12
    assert state["create_directories"] is True
    assert state["is_background"] is False
    # ``output`` alias dropped; ``stdout`` is single source of truth.
    assert "output" not in state


def test_activate_skill_render_contract_uses_snake_case_payload() -> None:
    """SkillActivateTool.execute emits snake_case ``has_resources`` (not
    ``hasResources``) after ADR-0102 — pin that for the renderer."""
    proj = _fixture_observe(
        "activate_skill",
        {
            "name": "demo",
            "title": "demo",
            "description": "d",
            "has_resources": True,
            "content": "<body>",
        },
    )
    assert proj == {
        "name": "demo",
        "title": "demo",
        "hasResources": True,
        "content": "<body>",
    }


def test_search_has_no_state_projection() -> None:
    """``search`` contract declares no state fields — projection is empty
    even when payload is populated (renderer reads args only)."""
    assert _fixture_observe("search", {"anything": "value"}) == {}
