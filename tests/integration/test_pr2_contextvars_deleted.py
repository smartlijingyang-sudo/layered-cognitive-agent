"""PR2 Task 5 - three ContextVars deleted (spec section H ContextVar deletion list).

After Task 5 lands:

1. ``_current_publish_session`` (``lca.plugins.events.publishers._session_publish``)
   is gone - ``RunSessionWriter`` / direct ``Session.append`` is the seam.
2. ``_current_cursor`` (``lca.infrastructure.observability.loop_cursor.coordinator.adapter``)
   is gone - cursor flows through explicit DI.
3. ``_current_reasoner_prompt`` (``lca.plugins.events.hooks.model_visible.reasoner_prompt``)
   is gone - prompt flows through explicit DI.

The getter aliases vanish with them (per brief verify grep):

- ``current_publish_session``
- ``current_cursor`` (and the long-form ``get_current_cursor`` /
  ``bind_current_cursor`` / ``reset_current_cursor`` are removed in the
  same edit since the ContextVar machinery that justified them is gone)
- ``current_reasoner_prompt`` / ``get_current_reasoner_prompt`` /
  ``bind_current_reasoner_prompt`` / ``reset_current_reasoner_prompt`` /
  ``install_reasoner_prompt`` / ``reset_reasoner_prompt``

``ModelVisibleHookAdapter.complete()`` accepts ``cursor`` + ``reasoner_prompt``
as explicit kwargs (no ContextVar push), and forwards them to the hook instead
of the previous per-call ContextVar lookup.

This test fails on the pre-Task-5 baseline (symbols still exist) and passes
after the deletions land.

Spec: docs/superpowers/specs/2026-09-15-session-write-path-design.md section H
"""

from __future__ import annotations

import importlib
import os


def _has_attr(module_path, attr):
    try:
        mod = importlib.import_module(module_path)
    except Exception:
        return False
    return hasattr(mod, attr)


def test_current_publish_session_contextvar_deleted():
    mod_path = "lca.plugins.events.publishers._session_publish"
    assert not _has_attr(mod_path, "_current_publish_session")
    assert not _has_attr(mod_path, "current_publish_session")
    assert _has_attr(mod_path, "publish_via_session")


def test_current_cursor_contextvar_deleted():
    mod_path = "lca.infrastructure.observability.loop_cursor.coordinator.adapter"
    assert not _has_attr(mod_path, "_current_cursor")
    assert not _has_attr(mod_path, "current_cursor")
    assert not _has_attr(mod_path, "get_current_cursor")
    assert not _has_attr(mod_path, "bind_current_cursor")
    assert not _has_attr(mod_path, "reset_current_cursor")


def test_current_reasoner_prompt_contextvar_deleted():
    mod_path = "lca.plugins.events.hooks.model_visible.reasoner_prompt"
    try:
        mod = importlib.import_module(mod_path)
    except Exception:
        return
    assert not hasattr(mod, "_current_reasoner_prompt")
    assert not hasattr(mod, "get_current_reasoner_prompt")
    assert not hasattr(mod, "bind_current_reasoner_prompt")
    assert not hasattr(mod, "reset_current_reasoner_prompt")
    assert not hasattr(mod, "install_reasoner_prompt")
    assert not hasattr(mod, "reset_reasoner_prompt")


def test_model_visible_hook_adapter_accepts_explicit_cursor_and_reasoner_prompt():
    import inspect

    from lca.plugins.events.hooks.model_visible.adapter import ModelVisibleHookAdapter

    init_src = inspect.getsource(ModelVisibleHookAdapter.__init__)
    # Strip comments to avoid false positives from prose references to
    # ``_cursor_provider`` in the explanation block.
    code_lines = [
        ln for ln in init_src.splitlines()
        if ln.lstrip().startswith("#") is False
    ]
    code_only = "\n".join(code_lines)
    assert "self._cursor_provider" not in code_only, (
        "ModelVisibleHookAdapter.__init__ must not store a ContextVar-backed "
        "cursor_provider attribute; cursor flows through explicit kwargs on complete()"
    )

    sig = inspect.signature(ModelVisibleHookAdapter.complete)
    params_list = list(sig.parameters.values())
    param_names = [p.name for p in params_list]
    has_var_keyword = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params_list)
    has_explicit = "cursor" in param_names and "reasoner_prompt" in param_names
    assert has_var_keyword or has_explicit, (
        f"complete() signature must accept cursor + reasoner_prompt; got {param_names}"
    )


def test_session_publish_test_file_deleted():
    assert not os.path.exists(
        "tests/plugins/events/publishers/test_session_publish.py"
    ), "test_session_publish.py tests ContextVar-bound state; deleted per inventory E3"
