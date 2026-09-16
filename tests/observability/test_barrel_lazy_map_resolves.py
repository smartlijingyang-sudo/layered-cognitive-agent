"""The observability barrel's PEP 562 lazy map must resolve.

`lca/infrastructure/observability/__init__.py` keeps the legacy journal storage
symbols out of eager import time by mapping each public name to
``(module, attribute)`` in `_LAZY_JOURNAL_SYMBOLS` and resolving it in
``__getattr__``. That indirection has no static link: dropping a name from the
target module — or from that module's own ``__all__`` — leaves the parent barrel
advertising a symbol that raises ``AttributeError`` on access, which is exactly
the failure this test exists to catch.
"""

from __future__ import annotations

import importlib

import lca.infrastructure.observability as observability_barrel


def test_every_lazy_journal_symbol_resolves() -> None:
    lazy = observability_barrel._LAZY_JOURNAL_SYMBOLS
    assert lazy, "expected the barrel to declare lazy journal symbols"

    dangling = []
    for name, (module_path, attr) in lazy.items():
        module = importlib.import_module(module_path)
        if not hasattr(module, attr):
            dangling.append(f"{name}: {module_path}.{attr}")

    assert not dangling, "lazy barrel entries that do not resolve:\n" + "\n".join(dangling)


def test_lazy_lookup_of_unknown_name_raises_attribute_error() -> None:
    # The barrel must fail loudly for a name it never claimed to export.
    import pytest

    with pytest.raises(AttributeError, match="has no attribute"):
        _ = observability_barrel.NotALazyJournalSymbol
