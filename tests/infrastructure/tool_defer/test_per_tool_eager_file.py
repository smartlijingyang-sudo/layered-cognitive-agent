"""Tests for per-tool eager loading and read-only audit (ADR-0256 §14, ADR-0279).

Contract invariants:
1. Wire assembly: eager read tools (listFiles, readFile, searchFiles, grepContent, globFiles)
   are present on the wire on turn 1 without requiring tool_search.
2. Write tools (writeFile, editFile, moveFiles) stay deferred until tool_search(namespace='file').
3. Read-only audit: none of the eager read tools mutate file contents, create files, or alter mtime.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from lca.infrastructure.computer.op.result import ComputerOpResult
from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import ToolDeferSession
from lca.infrastructure.tools.builder.builder import build_tools_from_manifest
from lca.infrastructure.tools.lca_computer import (
    CLOUD_SANDBOX_MANIFEST,
    LcaComputerExecutor,
)
from lca.infrastructure.tools.lca_computer.manifest import _READ_FILE_API_NAMES


def _collect_dir_state(target_dir: Path) -> dict[str, tuple[int, int, bytes]]:
    """Capture (size, mtime_ns, content) for all files under target_dir."""
    state = {}
    for root, _dirs, files in os.walk(target_dir):
        for name in files:
            p = Path(root) / name
            st = p.stat()
            state[str(p.relative_to(target_dir))] = (st.st_size, st.st_mtime_ns, p.read_bytes())
    return state


def _collect_dir_mtimes(target_dir: Path) -> dict[str, int]:
    """Capture directory mtime_ns."""
    mtimes = {}
    for root, _dirs, _ in os.walk(target_dir):
        p = Path(root)
        mtimes[str(p.relative_to(target_dir))] = p.stat().st_mtime_ns
    return mtimes


def test_wire_assembly_has_read_tools_and_defers_write_tools() -> None:
    """Wire tools include read-only file APIs on turn 1; write APIs remain deferred."""
    # Build tools from manifest
    tools = build_tools_from_manifest(
        CLOUD_SANDBOX_MANIFEST,
        executor=object(),  # Schema inspection only
    )
    # Also add core tool_search stub
    from tests.contracts.test_tool_namespace_contracts import _stub_tool

    tool_search = _stub_tool("tool_search", "core", eager=True)
    all_tools = [tool_search, *tools]

    session = ToolDeferSession(DeferPolicy.default())
    session.update_turn(all_tools)
    wire, catalog = session.render_turn()
    wire_names = {spec["function"]["name"] for spec in wire}

    # Invariant 1: All read file APIs are on the wire
    read_names = {api.value for api in _READ_FILE_API_NAMES}
    for read_name in read_names:
        assert read_name in wire_names, f"Expected read tool {read_name!r} to be eager on wire"

    # Invariant 2: Write file APIs are NOT on the wire
    write_names = {"writeFile", "editFile", "moveFiles"}
    for write_name in write_names:
        assert write_name not in wire_names, f"Expected write tool {write_name!r} to be deferred"

    # Invariant 3: Prompt catalog shows file write operations
    assert "- file:" in catalog
    assert "写操作" in catalog


def test_tool_search_loads_write_tools_and_clears_file_catalog() -> None:
    """Calling tool_search for 'file' exposes write tools and removes catalog entry."""
    tools = build_tools_from_manifest(
        CLOUD_SANDBOX_MANIFEST,
        executor=object(),
    )
    from tests.contracts.test_tool_namespace_contracts import _stub_tool

    tool_search = _stub_tool("tool_search", "core", eager=True)
    all_tools = [tool_search, *tools]

    session = ToolDeferSession(DeferPolicy.default())
    session.update_turn(all_tools)

    # Initially write tools deferred
    wire, catalog = session.render_turn()
    wire_names = {spec["function"]["name"] for spec in wire}
    assert "writeFile" not in wire_names
    assert "- file:" in catalog

    # Model loads file namespace
    payload = session.load_namespace("file")
    assert payload["namespace"] == "file"
    loaded_tool_names = {t["function"]["name"] for t in payload["tools"]}
    assert "writeFile" in loaded_tool_names
    assert "editFile" in loaded_tool_names
    assert "moveFiles" in loaded_tool_names

    # After loading, wire includes write tools and catalog line disappears
    wire_after, catalog_after = session.render_turn()
    wire_after_names = {spec["function"]["name"] for spec in wire_after}
    assert "writeFile" in wire_after_names
    assert "editFile" in wire_after_names
    assert "moveFiles" in wire_after_names
    assert "- file:" not in catalog_after


@pytest.mark.asyncio
async def test_read_tools_are_strictly_read_only(tmp_path: Path) -> None:
    """Audit: eager read tools produce no filesystem side effects or mutations."""
    # Setup test workspace
    sub_dir = tmp_path / "subdir"
    sub_dir.mkdir()
    file_a = tmp_path / "hello.txt"
    file_a.write_text("Hello world\nSecond line with keyword target\nThird line\n", encoding="utf-8")
    file_b = sub_dir / "nested.md"
    file_b.write_text("# Title\nMarkdown content here\n", encoding="utf-8")

    # Record baseline state before any tool execution
    baseline_files = _collect_dir_state(tmp_path)
    baseline_dirs = _collect_dir_mtimes(tmp_path)

    # Build local computer executor backed by local operations
    class DirectLocalOps:
        """Minimal local fs implementation for read audit testing."""

        async def list_files(self, *, directory_path: str = "") -> ComputerOpResult:
            p = Path(directory_path or tmp_path)
            files = [{"name": e.name, "path": str(e), "is_directory": e.is_dir()} for e in p.iterdir()]  # noqa: ASYNC240
            return ComputerOpResult(success=True, content="ok", state={"files": files})

        async def read_file(
            self, *, path: str, start_line: int | None = None, end_line: int | None = None
        ) -> ComputerOpResult:
            p = Path(path)
            lines = p.read_text(encoding="utf-8").splitlines(keepends=True)  # noqa: ASYNC240
            s = (start_line or 1) - 1
            e = end_line or len(lines)
            content = "".join(lines[s:e])
            return ComputerOpResult(success=True, content=content, state={"content": content})

        async def search_files(
            self, *, directory: str = "", keyword: str = "", file_type: str = "", **kwargs: Any
        ) -> ComputerOpResult:
            p = Path(directory or tmp_path)
            res = [str(f) for f in p.rglob("*") if keyword.lower() in f.name.lower()]  # noqa: ASYNC240
            return ComputerOpResult(success=True, content="ok", state={"results": res})

        async def grep_content(
            self, *, pattern: str, directory: str = "", file_pattern: str = "", recursive: bool = True, **kwargs: Any
        ) -> ComputerOpResult:
            p = Path(directory or tmp_path)
            matches = []
            for f in p.rglob(file_pattern or "*"):  # noqa: ASYNC240
                if f.is_file():
                    for idx, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                        if pattern in line:
                            matches.append({"path": str(f), "line": idx, "content": line})
            return ComputerOpResult(success=True, content="ok", state={"matches": matches})

        async def glob_files(self, *, pattern: str = "*", directory: str = "", **kwargs: Any) -> ComputerOpResult:
            p = Path(directory or tmp_path)
            matches = [{"path": str(f), "name": f.name} for f in p.glob(pattern)]  # noqa: ASYNC240
            return ComputerOpResult(success=True, content="ok", state={"files": matches})

    ops = DirectLocalOps()
    executor = LcaComputerExecutor(ops)
    tools = build_tools_from_manifest(
        CLOUD_SANDBOX_MANIFEST,
        executor=executor,
        invoke_fn=lambda exc, name, args: exc.invoke(name, args),
    )
    tools_by_name = {t.name: t for t in tools}

    # Execute all 5 eager read tools
    res_list = await tools_by_name["listFiles"].execute({"directory_path": str(tmp_path)})
    assert res_list.success is True

    res_read = await tools_by_name["readFile"].execute({"path": str(file_a), "start_line": 1, "end_line": 2})
    assert res_read.success is True
    assert "Hello world" in str(res_read.payload)

    res_search = await tools_by_name["searchFiles"].execute({"directory": str(tmp_path), "keyword": "nested"})
    assert res_search.success is True

    res_grep = await tools_by_name["grepContent"].execute({"directory": str(tmp_path), "pattern": "keyword"})
    assert res_grep.success is True

    res_glob = await tools_by_name["globFiles"].execute({"directory": str(tmp_path), "pattern": "*.txt"})
    assert res_glob.success is True

    # Audit: verify absolutely zero changes to the filesystem
    current_files = _collect_dir_state(tmp_path)
    current_dirs = _collect_dir_mtimes(tmp_path)

    # 1. No files added or removed
    assert set(current_files.keys()) == set(baseline_files.keys())

    # 2. File contents and sizes are identical
    for rel_path, (base_size, base_mtime, base_content) in baseline_files.items():
        curr_size, curr_mtime, curr_content = current_files[rel_path]
        assert curr_size == base_size, f"Size changed for {rel_path}"
        assert curr_content == base_content, f"Content changed for {rel_path}"
        assert curr_mtime == base_mtime, f"mtime changed for {rel_path}"

    # 3. Directory mtimes unchanged
    for rel_dir, base_mtime in baseline_dirs.items():
        curr_mtime = current_dirs[rel_dir]
        assert curr_mtime == base_mtime, f"Directory mtime changed for {rel_dir}"
