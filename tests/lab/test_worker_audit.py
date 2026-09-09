"""Tests for ADR-0211 §8 worker audit module.

Verifies the load-time audit pipeline:
- signature_rules W-1 ~ W-5 detect keyword-only / typed / forbidden params / typed return
- body_rules W-7 / W-8 / W-9 / W-10 detect try-except / receipt construction /
  retired symbols / defensive guards
- audit_worker() aggregates errors without raising
- load_all() with LCA_WORKER_AUDIT_MODE=raise fails loud on audit failures

Each scratch module is written to a real file under a tmp_path so
``inspect.getsource`` works and locations can be reported.
"""
from __future__ import annotations

import sys
import textwrap
import uuid
from pathlib import Path

import pytest

# Track every scratch dir we create so teardown can clean sys.modules / sys.path.
_SCRATCH_DIRS: list[Path] = []


def _make_worker_module(tmp_path: Path, source: str) -> str:
    """Write ``source`` to a real file under tmp_path and import it.

    Returns the dotted module path. Uses a uuid suffix so re-runs in the
    same session don't collide on sys.modules caching.
    """
    suffix = uuid.uuid4().hex[:8]
    pkg_root = tmp_path / f"scratch_{suffix}"
    pkg_root.mkdir(parents=True)
    (pkg_root / "__init__.py").write_text("")
    plugin_file = pkg_root / "plugin.py"
    plugin_file.write_text(textwrap.dedent(source).lstrip())
    name = f"scratch_{suffix}.plugin"
    sys.path.insert(0, str(tmp_path))
    _SCRATCH_DIRS.append(tmp_path)
    import importlib

    mod = importlib.import_module(name)
    return name, mod, plugin_file


# ---------------------------------------------------------------------------
# signature_rules W-1 ~ W-5
# ---------------------------------------------------------------------------


def test_w1_keyword_only_violation():
    import inspect

    from lca.plugins.lab.internal.audit.signature_rules import run as sig_run

    def f(decision: int) -> int:  # not keyword-only
        return decision

    sig = inspect.signature(f)
    errs = sig_run(sig, "<test:f>")
    assert any(e.rule_id == "W-1" for e in errs)


def test_w2_untyped_input():
    import inspect

    from lca.plugins.lab.internal.audit.signature_rules import run as sig_run

    def f(*, x):  # no annotation
        return x

    sig = inspect.signature(f)
    errs = sig_run(sig, "<test:f>")
    assert any(e.rule_id == "W-2" for e in errs)


def test_w2_dict_input_forbidden():
    import inspect

    from lca.plugins.lab.internal.audit.signature_rules import run as sig_run

    def f(*, x: dict) -> int:
        return 0

    sig = inspect.signature(f)
    errs = sig_run(sig, "<test:f>")
    assert any(e.rule_id == "W-2" for e in errs), [str(e) for e in errs]


def test_w3_forbidden_framework_params():
    import inspect

    from lca.plugins.lab.internal.audit.signature_rules import run as sig_run

    def f(*, ctx, decision: int):
        return decision

    sig = inspect.signature(f)
    errs = sig_run(sig, "<test:f>")
    assert any(e.rule_id == "W-3" for e in errs)


def test_w5_untyped_return():
    import inspect

    from lca.plugins.lab.internal.audit.signature_rules import run as sig_run

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


def test_audit_worker_clean(tmp_path):
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
    name, mod, _ = _make_worker_module(tmp_path, src)
    fn = mod.f
    errs = audit_worker(name, fn)
    assert errs == [], f"clean worker should have no audit errors, got: {errs}"


def test_audit_worker_aggregates_multiple_violations(tmp_path):
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
    name, mod, _ = _make_worker_module(tmp_path, src)
    fn = mod.f
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

    Builds a fake ``lca.plugins.lab._audit_raise`` namespace under tmp_path
    with a worker that violates W-2 / W-7 / W-9 / W-10, then monkeypatches
    the loader's _HOOK_PACKAGES to include it and forces a re-load.
    """
    from lca.plugins.lab.internal import loader as loader_mod

    # Build a real Python package tree mirroring lca.plugins.lab._audit_raise
    base = tmp_path / "lca" / "plugins" / "lab" / "_audit_raise"
    (base / "plugin").mkdir(parents=True)
    (tmp_path / "lca" / "__init__.py").write_text("")
    (tmp_path / "lca" / "plugins" / "__init__.py").write_text("")
    (tmp_path / "lca" / "plugins" / "lab" / "__init__.py").write_text("")
    (base / "__init__.py").write_text("")
    (base / "plugin" / "__init__.py").write_text("")
    (base / "plugin" / "plugin.py").write_text(
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
                    return register_worker("x", cls=None)
            '''
        )
    )

    sys.path.insert(0, str(tmp_path))
    # 显式 import 临时 plugin 模块并塞进 sys.modules,绕过 namespace package
    # 路径解析(真 lca.plugins.lab 已是 implicit namespace package)。
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "lca.plugins.lab._audit_raise.plugin",
        tmp_path / "lca" / "plugins" / "lab" / "_audit_raise" / "plugin" / "plugin.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lca.plugins.lab._audit_raise.plugin"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(
        loader_mod,
        "_HOOK_PACKAGES",
        loader_mod._HOOK_PACKAGES + ("lca.plugins.lab._audit_raise.plugin",),
    )
    monkeypatch.setattr(loader_mod, "_LOADED", False)
    monkeypatch.setenv("LCA_WORKER_AUDIT_MODE", "raise")

    from lca.plugins.lab.internal.audit import WorkerAuditFailure

    with pytest.raises(WorkerAuditFailure):
        loader_mod.load_all()
