"""Tests for the contract-level ``RegistryKeyError``.

The error lives in ``lca.contracts.exceptions.registry`` so harness and
cognition consumers depend on contracts, not the infrastructure registry.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from lca.contracts.exceptions.registry import RegistryKeyError

REPO = Path(__file__).resolve().parents[3]


def test_registry_key_error_is_value_error() -> None:
    assert issubclass(RegistryKeyError, ValueError)


def test_registry_key_error_carries_attributes() -> None:
    err = RegistryKeyError("tool.read", "action", ["tool.a", "tool.b"])
    assert err.key == "tool.read"
    assert err.registry_kind == "action"
    assert err.available == ["tool.a", "tool.b"]


def test_registry_key_error_message() -> None:
    err = RegistryKeyError("x", "注册表", ["a", "b"])
    assert "x" in str(err)
    assert "a" in str(err)


def test_raise_and_catch() -> None:
    with pytest.raises(RegistryKeyError):
        raise RegistryKeyError("k", "kind", [])


def test_infrastructure_registry_reexports_contracts_error() -> None:
    """Existing ``lca.infrastructure.component.registry`` consumers keep working."""
    infra = importlib.import_module("lca.infrastructure.component.registry")
    assert infra.RegistryKeyError is RegistryKeyError


def test_harness_dispatch_imports_error_from_contracts() -> None:
    source = (REPO / "lca" / "harness" / "declarative" / "execute" / "dispatch.py").read_text(
        encoding="utf-8"
    )
    assert "lca.contracts.exceptions.registry" in source
    assert "lca.infrastructure.component.registry" not in source
