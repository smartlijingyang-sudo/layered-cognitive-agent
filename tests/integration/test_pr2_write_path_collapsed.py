"""PR2 Task 4 — dual-writer surface path collapse pinned by this test.

The conversation-history write path is one writer with one append method per
event type. After Task 4 lands:

1. ``RunSessionWriter.append_user_message`` is the ONLY surface-write seam for
   user messages; the legacy ``accept_user_message`` / ``append_user_surface``
   / ``append_human_answer_surface`` are gone.
2. The fact-gateway bound helpers (``append_surface_bound``,
   ``_bound_publish_writer``, ``fact_gateway_for_emit``) are deleted; the
   remaining helpers are only ``append_catalog_bound`` and ``publish_ep_bound``
   (the spine/catalog durably-bound seams).
3. The dual-writer surface modules (``surface_emit``, ``tool_surface_emit``,
   ``_overflow_0``, ``lifecycle_emit``) are deleted; the
   ``_LifecycleState`` ContextVar is gone with them.
4. The shadow ``assemble_model_history`` helper is gone; the fold lives on
   the writer (``RunSessionWriter.derive_messages``).

This test fails on the pre-Task-4 baseline (symbols still exist) and passes
after the deletions land.
"""

from __future__ import annotations

import importlib


def _has_attr(module_path: str, attr: str) -> bool:
    try:
        mod = importlib.import_module(module_path)
    except Exception:
        return False
    return hasattr(mod, attr)


def test_surface_modules_are_deleted() -> None:
    """The dual-writer surface modules must not be importable."""
    assert not _has_attr("lca.infrastructure.session.emit.surface_emit", "append_user_surface")
    assert not _has_attr("lca.infrastructure.session.emit.tool_surface_emit", "append_tool_result_surface")
    assert not _has_attr("lca.infrastructure.session.emit.lifecycle_emit", "accept_user_message")
    # ``complete_model`` survives T4 (catalog-only path stays) — see brief Step 4.5.
    assert not _has_attr("lca.infrastructure.session.emit.lifecycle_emit", "_LifecycleState")


def test_overflow_module_is_deleted() -> None:
    """The ``_overflow_0`` shadow module must not be importable."""
    assert not _has_attr("lca.infrastructure.session._overflow_0.bindings", "assemble_model_history")
    assert not _has_attr("lca.infrastructure.session._overflow_0", "assemble_model_history")


def test_fact_gateway_bound_helpers_are_deleted() -> None:
    """The surface-bound helpers are gone; catalog/spine-bound remain."""
    assert not _has_attr("lca.loop.fact_gateway", "append_surface_bound")
    assert not _has_attr("lca.loop.fact_gateway", "_bound_publish_writer")
    assert not _has_attr("lca.loop.fact_gateway", "fact_gateway_for_emit")
    # The catalog-bound helpers (no surface) survive because the spec keeps
    # the catalog/spine seam.
    assert _has_attr("lca.loop.fact_gateway", "append_catalog_bound")
    assert _has_attr("lca.loop.fact_gateway", "publish_ep_bound")


def test_session_package_no_longer_exports_assemble_model_history() -> None:
    """``lca.infrastructure.session`` must not re-export the shadow helper."""
    pkg = importlib.import_module("lca.infrastructure.session")
    assert not hasattr(pkg, "assemble_model_history")


def test_runtime_loop_no_longer_calls_accept_user_message() -> None:
    """``accept_user_message`` is gone from the runtime loop path."""
    import lca.runtime.loop.runtime_loop as mod

    src = mod.__file__
    assert src is not None
    with open(src, encoding="utf-8") as f:
        text = f.read()
    assert "accept_user_message" not in text


def test_run_session_writer_exposes_append_user_message() -> None:
    """``RunSessionWriter.append_user_message`` is the only user-message seam."""
    from lca.runtime.session.run_session_writer import RunSessionWriter

    assert hasattr(RunSessionWriter, "append_user_message")
