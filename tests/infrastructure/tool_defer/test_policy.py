"""Tests for DeferPolicy (lca.infrastructure.tool_defer.policy)."""

from __future__ import annotations

import dataclasses

import pytest

from lca.infrastructure.tool_defer.policy import DeferPolicy


def test_default_policy_defers_everything_except_loader() -> None:
    policy = DeferPolicy.default()
    assert policy.enabled is True
    # The core namespace (holding tool_search) must stay eager.
    assert "core" in policy.eager_namespaces


def test_policy_is_frozen() -> None:
    policy = DeferPolicy.default()
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.enabled = False  # type: ignore[misc]


def test_policy_can_be_disabled() -> None:
    policy = DeferPolicy(enabled=False)
    assert policy.enabled is False
    assert "core" in policy.eager_namespaces


def test_namespace_description_override() -> None:
    policy = DeferPolicy(namespace_descriptions={"web": "Web browsing."})
    assert policy.namespace_descriptions["web"] == "Web browsing."
