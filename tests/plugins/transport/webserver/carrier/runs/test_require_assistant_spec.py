"""RA-045: require_assistant_spec is the public seam for assistant-spec resolution."""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.capabilities import ASSISTANT_CATALOG
from lca.contracts.mechanisms.capability.capability import MissingCapabilityError
from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import (
    require_assistant_spec,
)


class _FakeCatalog:
    def __init__(self, entries: dict[str, Any]) -> None:
        self._entries = entries

    def get(self, assistant_id: str) -> Any | None:
        return self._entries.get(assistant_id)


class _FakeScope:
    """Minimal Context stub: require(key) serves the assistant catalog."""

    def __init__(self, catalog: _FakeCatalog | None) -> None:
        self._catalog = catalog

    def require(self, key: str) -> Any:
        if key == ASSISTANT_CATALOG.key and self._catalog is not None:
            return self._catalog
        raise MissingCapabilityError(key)


def test_empty_id_returns_none_without_touching_catalog() -> None:
    # An empty id is the I-B8 no-assistant path: no catalog lookup at all,
    # so even a scope without the capability must not raise.
    assert require_assistant_spec(_FakeScope(None), "") is None
    assert require_assistant_spec(None, "") is None


def test_missing_catalog_raises_runtime_error() -> None:
    # assistant_id set but the catalog capability is missing: fail loud,
    # never a silent policy drop.
    with pytest.raises(RuntimeError, match=r"assistant\.catalog capability is missing"):
        require_assistant_spec(_FakeScope(None), "asst_1")


def test_catalog_miss_returns_none() -> None:
    scope = _FakeScope(_FakeCatalog({}))
    assert require_assistant_spec(scope, "asst_unknown") is None


def test_catalog_hit_returns_spec() -> None:
    spec = object()
    scope = _FakeScope(_FakeCatalog({"asst_1": spec}))
    assert require_assistant_spec(scope, "asst_1") is spec
