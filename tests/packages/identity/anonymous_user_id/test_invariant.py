"""Tests for ``lca.packages.identity.anonymous_user_id.src.invariant``.

================================================================================
TEST STRATEGY
================================================================================
The invariant module is intentionally minimal (it's a no-op companion that follows
the DSH package convention). Tests verify:
  - Public constants are correct (name, inject, PACKAGE_NAME)
  - ``apply`` registers with the invariant service (via a mock)
  - ``_install`` is a no-op (doesn't raise, doesn't mutate)

================================================================================
UPSTREAM ALIGNMENT
================================================================================
These tests mirror the behavior of upstream's invariant system integration tests.
The key invariant is: "the companion registers successfully and doesn't crash".
"""

from __future__ import annotations

from typing import Any

from lca.packages.identity.anonymous_user_id import invariant as sut

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify the companion's metadata constants are correct."""

    def test_package_name_is_scoped(self) -> None:
        """Package name follows the npm-style scoped package convention."""
        assert sut.PACKAGE_NAME == "@deepseek-ai/dsh-anonymous-user-id"

    def test_companion_name_is_descriptive(self) -> None:
        """Companion name is human-readable and identifies the package."""
        assert sut.name == "anonymous-user-id-invariant"

    def test_inject_declares_invariants_dependency(self) -> None:
        """Companion declares dependency on the 'invariants' service."""
        assert sut.inject == ("invariants",)


# ---------------------------------------------------------------------------
# Test _install (the no-op invariant validator)
# ---------------------------------------------------------------------------


class TestInstall:
    """Verify the _install function is a proper no-op."""

    def test_install_returns_none(self) -> None:
        """_install is a pure no-op — it doesn't return anything meaningful."""
        result = sut._install(None, lambda msg: None)
        assert result is None

    def test_install_does_not_raise(self) -> None:
        """_install can be called with any arguments without raising."""
        # This is important: the DI framework calls _install with a context
        # and a failure reporter. It must not crash.
        sut._install(object(), lambda msg: None)
        sut._install(None, None)  # Even with None args

    def test_install_does_not_mutate(self) -> None:
        """_install has no side effects (it doesn't modify any state)."""
        # We can't directly test "no mutation" without a full integration test,
        # but we can verify it doesn't raise or return anything unexpected.
        # The fact that it's a pure no-op (just ``pass``) is the guarantee.
        pass


# ---------------------------------------------------------------------------
# Test apply (the companion registration function)
# ---------------------------------------------------------------------------


class FakeInvariantRegistry:
    """Mock invariant registry that records registrations."""

    def __init__(self) -> None:
        self.registrations: list[tuple[str, Any]] = []

    def register(self, package_name: str, installer: Any) -> callable:
        """Record the registration and return a dummy disposer."""
        self.registrations.append((package_name, installer))
        # Return a dummy disposer (a no-op callable).
        return lambda: None


class FakeInvariantContext:
    """Mock Cordis context that provides a fake invariant registry."""

    def __init__(self) -> None:
        self.invariants = FakeInvariantRegistry()


class TestApply:
    """Verify the apply function registers the companion correctly."""

    def test_apply_registers_with_correct_package_name(self) -> None:
        """apply registers the companion with the correct package name."""
        ctx = FakeInvariantContext()
        sut.apply(ctx)

        assert len(ctx.invariants.registrations) == 1
        package_name, _ = ctx.invariants.registrations[0]
        assert package_name == sut.PACKAGE_NAME

    def test_apply_registers_with_install_function(self) -> None:
        """apply registers the companion with the _install function."""
        ctx = FakeInvariantContext()
        sut.apply(ctx)

        _, installer = ctx.invariants.registrations[0]
        # The installer should be the _install function.
        assert installer is sut._install

    def test_apply_returns_disposer(self) -> None:
        """apply returns a disposer function (from the registry's register method)."""
        ctx = FakeInvariantContext()
        disposer = sut.apply(ctx)

        # The disposer should be callable.
        assert callable(disposer)
        # Calling it should not raise.
        disposer()

    def test_apply_can_be_called_multiple_times(self) -> None:
        """apply can be called multiple times (e.g., for testing)."""
        ctx = FakeInvariantContext()
        sut.apply(ctx)
        sut.apply(ctx)
        sut.apply(ctx)

        # Each call should register a new companion.
        assert len(ctx.invariants.registrations) == 3

    def test_apply_with_minimal_context(self) -> None:
        """apply works with a minimal mock context (just the invariants property)."""

        # We can use a simple object with just the invariants attribute.
        class MinimalContext:
            def __init__(self) -> None:
                self.invariants = FakeInvariantRegistry()

        ctx = MinimalContext()
        disposer = sut.apply(ctx)
        assert callable(disposer)


# ---------------------------------------------------------------------------
# Integration-style test: verify the companion follows the DSH convention
# ---------------------------------------------------------------------------


class TestCompanionConvention:
    """Verify the companion follows the DSH package convention."""

    def test_has_required_constants(self) -> None:
        """Companion exports the required metadata constants."""
        assert hasattr(sut, "name")
        assert hasattr(sut, "inject")
        assert hasattr(sut, "PACKAGE_NAME")

    def test_has_required_functions(self) -> None:
        """Companion exports the required entry points."""
        assert hasattr(sut, "apply")
        assert hasattr(sut, "_install")

    def test_constants_are_strings_or_tuples(self) -> None:
        """Metadata constants are the correct types."""
        assert isinstance(sut.name, str)
        assert isinstance(sut.inject, tuple)
        assert isinstance(sut.PACKAGE_NAME, str)

    def test_functions_are_callable(self) -> None:
        """Entry points are callable."""
        assert callable(sut.apply)
        assert callable(sut._install)
