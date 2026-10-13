"""RA-133: pin approved-names ContextVar inheritance across create_task.

The isolation argument for approved tool names ("injection lives and dies
with the resume task") rests on ContextVar semantics:
``RegistryRunCommands.resume_approval`` (commands.py) spawns
``asyncio.create_task(resume_run(...))``; ``resume_run`` (execute.py) calls
``set_approved_tool_names`` inside that child task. ``create_task`` copies
the current context, so the child inherits the parent's values at creation
time, and the child's own ``set_`` never leaks back to the parent.

These tests pin both directions against the real seam (no monkeypatching
of the seam itself); the 7ecb54c6c tests bypass the ContextVar and the
facade test does set->get inside a single task, so neither covers this.
"""

from __future__ import annotations

import asyncio

import pytest

from lca.infrastructure.runtime_plane.access.approved_tools import (
    get_approved_tool_names,
    set_approved_tool_names,
)


@pytest.mark.asyncio
async def test_child_task_inherits_parent_approved_names() -> None:
    """Parent sets approved names; the create_task child sees them."""
    set_approved_tool_names(frozenset({"executeCode"}))
    try:
        seen: dict[str, frozenset[str]] = {}

        async def child() -> None:
            seen["names"] = get_approved_tool_names()

        await asyncio.create_task(child())
        assert seen["names"] == frozenset({"executeCode"})
    finally:
        # Keep the ContextVar clean for sibling tests.
        set_approved_tool_names(frozenset())


@pytest.mark.asyncio
async def test_child_task_injection_is_invisible_to_parent() -> None:
    """Child (like resume_run) injects names; the parent never sees them."""

    async def stub_resume_body() -> frozenset[str]:
        # Mirrors execute.resume_run: inject inside the resume task, then the
        # coordinator reads the injection via get_approved_tool_names().
        set_approved_tool_names(frozenset({"executeCode"}))
        return get_approved_tool_names()

    parent_before = get_approved_tool_names()
    child_saw = await asyncio.create_task(stub_resume_body())
    parent_after = get_approved_tool_names()

    assert child_saw == frozenset({"executeCode"})
    assert parent_before == frozenset()
    assert parent_after == frozenset()
