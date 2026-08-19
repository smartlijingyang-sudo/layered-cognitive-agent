"""Tests for invariant.py - the invariant companion module.

================================================================================
TEST STRATEGY
================================================================================
This test file covers the invariant companion module:
  - Companion metadata exports (name, inject, PACKAGE_NAME)
  - Apply function registration
  - Dispose function behavior
  - No-op installer behavior

================================================================================
UPSTREAM ALIGNMENT
================================================================================
These tests verify 1:1 behavioral parity with the upstream TypeScript implementation.
"""

from __future__ import annotations

from unittest.mock import Mock

from lca.packages.runtime_diagnostics.invariants.src import invariant


def test_companion_metadata_name() -> None:
    """Test that the companion name is correctly exported."""
    assert invariant.name == "invariants-invariant"


def test_companion_metadata_inject() -> None:
    """Test that the inject list is correctly exported."""
    assert invariant.inject == ["invariants"]


def test_companion_metadata_package_name() -> None:
    """Test that the PACKAGE_NAME constant is correctly defined."""
    assert invariant.PACKAGE_NAME == "@deepseek-ai/dsh-invariants"


def test_install_is_noop() -> None:
    """Test that the _install function is a no-op."""
    # The _install function should not raise any exceptions
    # and should not perform any operations
    ctx = Mock()
    fail = Mock()

    # Call the _install function
    result = invariant._install(ctx, fail)

    # Verify it returns None (no-op)
    assert result is None

    # Verify ctx and fail were not called
    ctx.assert_not_called()
    fail.assert_not_called()


def test_apply_registers_companion() -> None:
    """Test that apply() registers the companion with the registry."""
    # Create a mock context with an invariants registry
    mock_registry = Mock()
    mock_dispose = Mock()
    mock_registry.register.return_value = mock_dispose

    mock_ctx = Mock()
    mock_ctx.invariants = mock_registry

    # Call apply
    dispose = invariant.apply(mock_ctx)

    # Verify the registry.register was called with correct arguments
    mock_registry.register.assert_called_once_with(invariant.PACKAGE_NAME, invariant._install)

    # Verify the dispose function is returned
    assert dispose is mock_dispose


def test_apply_returns_dispose_function() -> None:
    """Test that apply() returns a dispose function."""
    # Create a mock context with an invariants registry
    mock_registry = Mock()
    mock_dispose = Mock()
    mock_registry.register.return_value = mock_dispose

    mock_ctx = Mock()
    mock_ctx.invariants = mock_registry

    # Call apply
    dispose = invariant.apply(mock_ctx)

    # Verify the dispose function can be called
    dispose()
    mock_dispose.assert_called_once()


def test_all_exports() -> None:
    """Test that __all__ contains the correct exports."""
    assert set(invariant.__all__) == {"name", "inject", "apply"}
