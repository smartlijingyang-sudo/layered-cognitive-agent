"""Tests for ADR-0211 §8 worker audit module.

Verifies the load-time audit pipeline:
- signature_rules W-1 ~ W-5 detect keyword-only / typed / forbidden params / typed return
- body_rules W-7 / W-8 / W-9 / W-10 detect try-except / receipt construction /
  retired symbols / defensive guards
- audit_worker() aggregates errors without raising
- load_all() with LCA_WORKER_AUDIT_MODE=raise fails loud on audit failures

Each test creates a temporary module under lca.plugins.lab.<stage>.<basename>/plugin.py
so it can be discovered by the loader, then runs the audit pipeline.
"""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest


# All test plugins live under this scratch directory so they don't pollute
# the real plugin tree. We use sys.modules caching + a runtime-loaded module
# object instead of writing to disk to keep the test hermetic.
SCRATCH_MODULES: dict[str, object] = {}


def _make_worker_module(name: str, source: str) -> str:
    """Compile ``source`` as a fake module and register it under ``name``.

    Returns the module path so audit_worker / discover_worker can resolve it.
    The fake module lives in sys.modules and is introspectable via
    inspect.signature / inspect.getsource.
    """
    import types

    code = textwrap.dedent(source).lstrip()
    module = types.ModuleType(name)
    module.__file__ = f"<test:{name}>"
    exec(compile(code, module.__file__, "exec"), module.__dict__)
    sys.modules[name] = module
    SCRATCH_MODULES[name] = module
    return name


# ---------------------------------------------------------------------------
# signature_rules W-1 ~ W-5
# ---------------------------------------------------------------------------


def test_w1_keyword_only_violation():
    from lca.plugins.lab.internal.audit import audit_worker
    from lca.plugins.lab.internal.audit.signature_rules import run as sig_run
    import inspect

    def f(decision: int) -> int:  # not keyword-only
        return decision

    sig = inspect.signature(f)
    errs = sig_run(sig, "<test:f>")
    assert any(e.rule_id == "W-1" for e in errs)


def test_w2_untyped_input():
    from lca.plugins.lab.internal.audit.signature_rules import run as sig_run
    import inspect

    def f(*, x):  # no annotation
        return x

    sig = inspect.signature(f)
    errs = sig_run(sig, "<test:f>")
    assert any(e.rule_id == "W-2" for e in errs)


def test_w2_dict_input_forbidden():
    from lca.plugins.lab.internal.audit.signature_rules import run as sig_run
    import inspect

    def f(*, x: dict) -> int:
        return 0

    sig = inspect.signature(f)
    errs = sig_run(sig, "<test:f>")
    assert any(e.rule_id == "W-2" for e in errs), [str(e) for e in errs]


def test_w3_forbidden_framework_params():
    from lca.plugins.lab.internal.audit.signature_rules import run as sig_run
    import inspect

    def f(*, ctx, decision: int):
        return decision

    sig = inspect.signature(f)
    errs = sig_run(sig, "<test:f>")
    assert any(e.rule_id == "W-3" for e in errs)


def test_w5_untyped_return():
    from lca.plugins.lab.internal.audit.signature_rules import run as sig_run
    import inspect

    def f(*, x: int):  # no return annotation
        return x

    sig = inspect.signature(f)
    errs = sig_run(sig, "<test:f>")
    assert any(e.rule_id == "W-5" for e in errs)


# ---------------------------------------------------------------------------
# body_rules W-7 / W-8 / W-9 / W-10
# ---------------------------------------------------------------------------


def test_w7_no_try_except():
    from lca.plugins.lab.internal.audit.body_rules import run as body_run

    src = textwrap.dedent(
        """
        def f(*, x: int) -> int:
            try:
                return x + 1
            except Exception:
                return 0
        """
    )
    errs = body_run(src, "<test:f>")
    assert any(e.rule_id == "W-7" for e in errs)


def test_w8_no_receipt_construction():
    from lca.plugins.lab.internal.audit.body_rules import run as body_run

    src = textwrap.dedent(
        """
        def f(*, x: int) -> int:
            return Receipt(ok=False)
        """
    )
    errs = body_run(src, "<test:f>")
    assert any(e.rule_id == "W-8" for e in errs)


def test_w9_no_retired_symbols():
    from lca.plugins.lab.internal.audit.body_rules import run as body_run

    src = textwrap.dedent(
        """
        def f(*, x: int) -> int:
            return register_worker("x", cls=None)
        """
    )
    errs = body_run(src, "<test:f>")
    assert any(e.rule_id == "W-9" for e in errs)


def test_w10_no_defensive_guards():
    from lca.plugins.lab.internal.audit.body_rules import run as body_run

    src = textwrap.dedent(
        """
        def f(*, x: int | None) -> int:
            if x is None:
                return 0
            return x
        """
    )
    errs = body_run(src, "<test:f>")
    assert any(e.rule_id == "W-10" for e in errs)


def test_w10_no_getattr_default():
    from lca.plugins.lab.internal.audit.body_rules import run as body_run

    src = textwrap.dedent(
        """
        def f(*, x: object) -> str:
            return getattr(x, "name", "default")
        """
    )
    errs = body_run(src, "<test:f>")
    assert any(e.rule_id == "W-10" for e in errs)


# ---------------------------------------------------------------------------
# audit_worker aggregate
# ---------------------------------------------------------------------------


def test_audit_worker_clean():
    """干净 worker (no audit errors) returns empty list."""
    from lca.plugins.lab.internal.audit import audit_worker

    src = textwrap.dedent(
        """
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class Out:
            v: int

        def f(*, x: int) -> Out:
            return Out(v=x + 1)
        """
    )
    name = _make_worker_module("lca.plugins.lab._audit_test.clean", src)
    # audit_worker needs a worker_fn to introspect — find it
    fn = sys.modules[name].f
    errs = audit_worker(name, fn)
    assert errs == [], f"clean worker should have no audit errors, got: {errs}"


def test_audit_worker_aggregates_multiple_violations():
    """A bad worker accumulates all violations."""
    from lca.plugins.lab.internal.audit import audit_worker

    src = textwrap.dedent(
        """
        def f(*, ctx, x: dict):
            try:
                if x is None:
                    return {}
                return x
            except Exception:
                return register_worker("x", cls=None)
        """
    )
    name = _make_worker_module("lca.plugins.lab._audit_test.bad", src)
    fn = sys.modules[name].f
    errs = audit_worker(name, fn)
    rule_ids = {e.rule_id for e in errs}
    assert "W-2" in rule_ids
    assert "W-3" in rule_ids
    assert "W-7" in rule_ids
    assert "W-9" in rule_ids
    assert "W-10" in rule_ids


# ---------------------------------------------------------------------------
# loader integration with LCA_WORKER_AUDIT_MODE=raise
# ---------------------------------------------------------------------------


def test_loader_audit_mode_raise_fails_loud(monkeypatch, tmp_path):
    """LCA_WORKER_AUDIT_MODE=raise → load_all() raises on audit failure.

    Writes a real (bad) worker plugin into tmp_path, then dynamically adds
    tmp_path to the loader's _HOOK_PACKAGES so load_all() picks it up.
    """
    from lca.plugins.lab.internal import loader as loader_mod

    bad_plugin_dir = tmp_path / "lca" / "plugins" / "lab" / "_audit_raise" / "plugin"
    bad_plugin_dir.mkdir(parents=True)
    (tmp_path / "lca" / "plugins" / "lab" / "_audit_raise" / "__init__.py").write_text("")
    (tmp_path / "lca" / "plugins" / "lab" / "_audit_raise" / "plugin" / "__init__.py").write_text("")
    (bad_plugin_dir / "plugin.py").write_text(
        textwrap.dedent(
            '''
            """test worker.

            worker: f(*, x)
            kind: TRANSFORMER
            out_port: out
            """
            from typing import Any

            def f(*, x: Any) -> Any:
                try:
                    if x is None:
                        return {}
                    return x
                except Exception:
                    return x
            '''
        )
    )

    monkeypatch.setitem(sys.path, 0, str(tmp_path))
    monkeypatch.setattr(
        loader_mod, "_HOOK_PACKAGES", loader_mod._HOOK_PACKAGES + ("lca.plugins.lab._audit_raise.plugin",)
    )
    monkeypatch.setattr(loader_mod, "_LOADED", False)
    monkeypatch.setenv("LCA_WORKER_AUDIT_MODE", "raise")

    from lca.plugins.lab.internal.audit import WorkerAuditFailure

    with pytest.raises(WorkerAuditFailure):
        loader_mod.load_all()