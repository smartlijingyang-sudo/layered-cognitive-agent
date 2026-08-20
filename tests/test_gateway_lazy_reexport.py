"""Regression: `gateway.__init__` lazy re-exports must not recurse.

PR-0 origin story
-----------------
`gateway/__init__.py` introduced module-level `__getattr__` in dd10a43c
to defer Starlette app construction away from `import gateway`. The
implementation was ``from gateway import app as _app`` inside the hook,
which itself re-invoked the same `__getattr__('app')` and recurses
forever. The path that triggered it (``from gateway import app``) was
not exercised by the existing test suite, so the bug stayed dormant.

Contract after PR-0
-------------------
Python's native submodule mechanism handles ``gateway.app`` (it is the
``app.py`` file in the package, accessed as ``gateway.app`` /
``from gateway import app``). It does NOT go through `__getattr__`.

`__getattr__` only re-exports two callables (``create_app``,
``get_registry``) from ``gateway.app``, so consumers can write
``from gateway import create_app`` without first forcing
``gateway.app`` to load. This test exercises every documented
lazy-reexport path so the bug cannot regress without an immediate
red light.

Rules under test
----------------
1. ``import gateway`` does NOT eagerly import ``gateway.app``.
2. ``from gateway import create_app`` / ``get_registry`` resolve via
   the narrow ``__getattr__`` hook to the callables inside
   ``gateway.app``.
4. Unknown names raise the standard ``ImportError`` from a failed
   ``from X import Y`` lookup.
5. ``__getattr__('app')`` is NOT consulted for ``app`` — Python's
   submodule machinery resolves it directly to ``gateway.app``.
"""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def _isolate_gateway_modules():  # vulture: ignore  — pytest autouse fixture
    """Drop cached modules so each test starts with a fresh `gateway`."""
    for mod_name in list(sys.modules):
        if mod_name == "gateway" or mod_name.startswith("gateway."):
            del sys.modules[mod_name]
    yield
    # Clean up so subsequent tests see a fresh state too.
    for mod_name in list(sys.modules):
        if mod_name == "gateway" or mod_name.startswith("gateway."):
            del sys.modules[mod_name]


def test_import_gateway_does_not_load_app_submodule():
    import gateway  # noqa: F401  — side-effect import under test

    assert "gateway" in sys.modules
    assert "gateway.app" not in sys.modules, (
        "importing `gateway` must stay lazy — the Starlette app must "
        "not be constructed until something actually asks for it."
    )


def test_from_gateway_import_create_app_returns_callable():
    from gateway import create_app

    assert callable(create_app)
    assert create_app is sys.modules["gateway.app"].create_app


def test_from_gateway_import_get_registry_returns_callable():
    from gateway import get_registry

    assert callable(get_registry)
    assert get_registry is sys.modules["gateway.app"].get_registry


def test_from_gateway_import_app_resolves_to_submodule():
    """`app` is a real submodule; Python resolves it without our hook.

    This is the canonical path that the pre-PR-0 bug recursed on. Today
    it must terminate quickly: Python's submodule machinery answers
    directly, never invoking `gateway.__getattr__`.
    """
    from gateway import app

    assert app is sys.modules["gateway.app"]
    assert app.__name__ == "gateway.app"


def test_unknown_name_raises_import_error():
    with pytest.raises(ImportError):
        # The `from X import Y` form wraps AttributeError in ImportError.
        from gateway import definitely_not_an_attribute  # noqa: F401


def test_getattr_does_not_recurse_on_create_app():
    """Direct probe: invoking `__getattr__('create_app')` must terminate.

    The pre-PR-0 bug exhausted Python's default recursion limit (1000)
    on the analogous call for `app`. A re-introduction of the
    `from gateway import app as _app` pattern inside the hook would
    trigger RecursionError here.
    """
    gateway_mod = importlib.import_module("gateway")
    # No artificial limit — default 1000 is plenty. A recursing __getattr__
    # would exhaust it before returning.
    create_app = gateway_mod.__getattr__("create_app")
    assert callable(create_app)
    assert create_app is sys.modules["gateway.app"].create_app


def test_getattr_raises_attribute_error_for_unknown_name():
    """`__getattr__` itself must raise AttributeError, not ImportError.

    `from gateway import X` wraps AttributeError in ImportError (test
    above). But if a caller invokes `gateway.__getattr__('X')` directly
    for an unknown name, the original AttributeError must surface
    unaltered so Python's import machinery can do its wrapping.
    """
    gateway_mod = importlib.import_module("gateway")
    with pytest.raises(AttributeError):
        gateway_mod.__getattr__("definitely_not_an_attribute")
