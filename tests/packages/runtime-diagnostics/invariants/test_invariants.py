"""Tests for runtime-diagnostics/invariants package.

================================================================================
TEST STRATEGY
================================================================================
This test file covers the main InvariantRegistry functionality:
  - Config validation (allowlist/blocklist patterns)
  - Package registration and filtering
  - Installer invocation and error handling
  - Disposal and cleanup
  - Error messages and exception types

================================================================================
UPSTREAM ALIGNMENT
================================================================================
These tests verify 1:1 behavioral parity with the upstream TypeScript implementation.
Each test corresponds to a specific behavior documented in the upstream code.
"""

from __future__ import annotations

import pytest

from lca.packages.runtime_diagnostics.invariants import (
    Config,
    InvariantError,
    InvariantRegistry,
)

# ---------------------------------------------------------------------------
# Test: Config dataclass
# ---------------------------------------------------------------------------


class TestConfig:
    """Tests for the Config dataclass."""

    def test_default_config(self) -> None:
        """Default config should have enabled=True and empty lists."""
        config = Config()
        assert config.enabled is True
        assert config.package_allowlist == []
        assert config.package_blocklist == []

    def test_custom_config(self) -> None:
        """Custom config should accept all fields."""
        config = Config(
            enabled=False,
            package_allowlist=["^test-.*"],
            package_blocklist=["^test-dev-.*"],
        )
        assert config.enabled is False
        assert config.package_allowlist == ["^test-.*"]
        assert config.package_blocklist == ["^test-dev-.*"]


# ---------------------------------------------------------------------------
# Test: InvariantError exception
# ---------------------------------------------------------------------------


class TestInvariantError:
    """Tests for the InvariantError exception class."""

    def test_error_message_format(self) -> None:
        """Error message should include package name and message."""
        error = InvariantError("my-package", "database connection failed")
        assert str(error) == 'invariant violated by "my-package": database connection failed'
        assert error.package_name == "my-package"
        assert error.code == "INVARIANT"
        assert error.name == "InvariantError"

    def test_error_is_exception(self) -> None:
        """InvariantError should be an Exception subclass."""
        error = InvariantError("pkg", "msg")
        assert isinstance(error, Exception)

    def test_error_can_be_raised(self) -> None:
        """InvariantError should be raisable and catchable."""
        with pytest.raises(InvariantError) as exc_info:
            raise InvariantError("test-pkg", "test message")

        assert exc_info.value.package_name == "test-pkg"
        assert str(exc_info.value) == 'invariant violated by "test-pkg": test message'


# ---------------------------------------------------------------------------
# Test: InvariantRegistry initialization
# ---------------------------------------------------------------------------


class TestInvariantRegistryInit:
    """Tests for InvariantRegistry initialization."""

    def test_default_initialization(self) -> None:
        """Registry should initialize with default config."""
        registry = InvariantRegistry()
        assert registry.enabled is True
        assert registry.package_allowlist == []
        assert registry.package_blocklist == []
        assert registry.registrations == set()

    def test_initialization_with_config(self) -> None:
        """Registry should initialize with custom config."""
        config = Config(
            enabled=False,
            package_allowlist=["^test-.*"],
            package_blocklist=["^test-dev-.*"],
        )
        registry = InvariantRegistry(config=config)

        assert registry.enabled is False
        assert len(registry.package_allowlist) == 1
        assert len(registry.package_blocklist) == 1
        assert registry.registrations == set()

    def test_initialization_with_context(self) -> None:
        """Registry should accept a context parameter."""
        ctx = object()
        registry = InvariantRegistry(ctx=ctx)
        assert registry._ctx is ctx


# ---------------------------------------------------------------------------
# Test: Config validation
# ---------------------------------------------------------------------------


class TestConfigValidation:
    """Tests for config pattern validation."""

    def test_empty_pattern_rejected(self) -> None:
        """Empty patterns should be rejected."""
        with pytest.raises(ValueError, match="must be non-blank"):
            InvariantRegistry(config=Config(package_allowlist=[""]))

    def test_whitespace_pattern_rejected(self) -> None:
        """Patterns with surrounding whitespace should be rejected."""
        with pytest.raises(ValueError, match="must be non-blank"):
            InvariantRegistry(config=Config(package_allowlist=[" test "]))

    def test_duplicate_pattern_rejected(self) -> None:
        """Duplicate patterns should be rejected."""
        with pytest.raises(ValueError, match="contains duplicate regex"):
            InvariantRegistry(config=Config(package_allowlist=["test", "test"]))

    def test_invalid_regex_rejected(self) -> None:
        """Invalid regex patterns should be rejected."""
        with pytest.raises(ValueError, match="contains invalid regex"):
            InvariantRegistry(config=Config(package_allowlist=["[invalid"]))

    def test_valid_patterns_accepted(self) -> None:
        """Valid regex patterns should be accepted."""
        registry = InvariantRegistry(
            config=Config(
                package_allowlist=["^test-.*", "^prod-.*"],
                package_blocklist=["-dev$"],
            )
        )
        assert len(registry.package_allowlist) == 2
        assert len(registry.package_blocklist) == 1


# ---------------------------------------------------------------------------
# Test: Package registration
# ---------------------------------------------------------------------------


class TestPackageRegistration:
    """Tests for package registration."""

    def test_register_valid_package(self) -> None:
        """Valid package names should be registered."""
        registry = InvariantRegistry()

        def installer(ctx, fail):
            pass

        dispose = registry.register("my-package", installer)
        assert "my-package" in registry.registrations
        assert callable(dispose)

    def test_register_empty_name_rejected(self) -> None:
        """Empty package names should be rejected."""
        registry = InvariantRegistry()

        with pytest.raises(ValueError, match="must be non-blank"):
            registry.register("", lambda ctx, fail: None)

    def test_register_whitespace_name_rejected(self) -> None:
        """Package names with whitespace should be rejected."""
        registry = InvariantRegistry()

        with pytest.raises(ValueError, match="must be non-blank"):
            registry.register("my package", lambda ctx, fail: None)

    def test_register_leading_trailing_whitespace_rejected(self) -> None:
        """Package names with leading/trailing whitespace should be rejected."""
        registry = InvariantRegistry()

        with pytest.raises(ValueError, match="must be non-blank"):
            registry.register(" my-package ", lambda ctx, fail: None)

    def test_register_duplicate_rejected(self) -> None:
        """Duplicate package registrations should be rejected."""
        registry = InvariantRegistry()

        registry.register("my-package", lambda ctx, fail: None)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("my-package", lambda ctx, fail: None)

    def test_installer_called_on_register(self) -> None:
        """Installer should be called when package is registered."""
        registry = InvariantRegistry()
        called = []

        def installer(ctx, fail):
            called.append(True)

        registry.register("my-package", installer)
        assert called == [True]

    def test_installer_not_called_when_disabled(self) -> None:
        """Installer should not be called when registry is disabled."""
        registry = InvariantRegistry(config=Config(enabled=False))
        called = []

        def installer(ctx, fail):
            called.append(True)

        registry.register("my-package", installer)
        assert called == []


# ---------------------------------------------------------------------------
# Test: Package filtering
# ---------------------------------------------------------------------------


class TestPackageFiltering:
    """Tests for package filtering logic."""

    def test_allowlist_filter(self) -> None:
        """Only packages matching allowlist should be checked."""
        registry = InvariantRegistry(config=Config(package_allowlist=["^test-.*"]))

        # Package matching allowlist
        called = []
        registry.register("test-package", lambda ctx, fail: called.append("test"))
        assert called == ["test"]

        # Package not matching allowlist
        registry.register("prod-package", lambda ctx, fail: called.append("prod"))
        assert called == ["test"]  # prod-package installer not called

    def test_blocklist_filter(self) -> None:
        """Packages matching blocklist should not be checked."""
        registry = InvariantRegistry(config=Config(package_blocklist=["-dev$"]))

        # Package not matching blocklist
        called = []
        registry.register("prod-package", lambda ctx, fail: called.append("prod"))
        assert called == ["prod"]

        # Package matching blocklist
        registry.register("test-dev", lambda ctx, fail: called.append("dev"))
        assert called == ["prod"]  # test-dev installer not called

    def test_allowlist_and_blocklist_combined(self) -> None:
        """Allowlist and blocklist should work together."""
        registry = InvariantRegistry(
            config=Config(
                package_allowlist=["^test-.*"],
                package_blocklist=["-dev$"],
            )
        )

        called = []

        # Matches allowlist, not blocklist -> checked
        registry.register("test-prod", lambda ctx, fail: called.append("prod"))

        # Matches allowlist and blocklist -> not checked
        registry.register("test-dev", lambda ctx, fail: called.append("dev"))

        # Doesn't match allowlist -> not checked
        registry.register("prod-package", lambda ctx, fail: called.append("other"))

        assert called == ["prod"]


# ---------------------------------------------------------------------------
# Test: Installer error handling
# ---------------------------------------------------------------------------


class TestInstallerErrorHandling:
    """Tests for installer error handling."""

    def test_installer_failure_raises_invariant_error(self) -> None:
        """Installer calling fail() should raise InvariantError."""
        registry = InvariantRegistry()

        def installer(ctx, fail):
            fail("database connection required")

        with pytest.raises(InvariantError) as exc_info:
            registry.register("my-package", installer)

        assert exc_info.value.package_name == "my-package"
        assert "database connection required" in str(exc_info.value)

    def test_installer_exception_removes_registration(self) -> None:
        """Installer exception should remove the registration."""
        registry = InvariantRegistry()

        def installer(ctx, fail):
            raise RuntimeError("installer failed")

        with pytest.raises(RuntimeError):
            registry.register("my-package", installer)

        assert "my-package" not in registry.registrations


# ---------------------------------------------------------------------------
# Test: Disposal
# ---------------------------------------------------------------------------


class TestDisposal:
    """Tests for disposal functionality."""

    def test_dispose_removes_registration(self) -> None:
        """Dispose function should remove the registration."""
        registry = InvariantRegistry()

        dispose = registry.register("my-package", lambda ctx, fail: None)
        assert "my-package" in registry.registrations

        dispose()
        assert "my-package" not in registry.registrations

    def test_dispose_can_be_called_multiple_times(self) -> None:
        """Dispose function should be idempotent."""
        registry = InvariantRegistry()

        dispose = registry.register("my-package", lambda ctx, fail: None)

        # Should not raise
        dispose()
        dispose()
        dispose()

        assert "my-package" not in registry.registrations

    def test_can_reregister_after_dispose(self) -> None:
        """Should be able to register again after disposal."""
        registry = InvariantRegistry()

        dispose1 = registry.register("my-package", lambda ctx, fail: None)
        dispose1()

        # Should succeed
        dispose2 = registry.register("my-package", lambda ctx, fail: None)
        assert "my-package" in registry.registrations


# ---------------------------------------------------------------------------
# Test: Context passing
# ---------------------------------------------------------------------------


class TestContextPassing:
    """Tests for context passing to installers."""

    def test_context_passed_to_installer(self) -> None:
        """Context should be passed to installer."""
        ctx = {"db": "connection"}
        registry = InvariantRegistry(ctx=ctx)

        received_ctx = []

        def installer(ctx, fail):
            received_ctx.append(ctx)

        registry.register("my-package", installer)
        assert received_ctx == [{"db": "connection"}]

    def test_fail_reporter_bound_to_package(self) -> None:
        """Fail reporter should be bound to the package name."""
        registry = InvariantRegistry()

        def installer(ctx, fail):
            fail("test error")

        with pytest.raises(InvariantError) as exc_info:
            registry.register("my-package", installer)

        assert exc_info.value.package_name == "my-package"


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases."""

    def test_multiple_registrations(self) -> None:
        """Should handle multiple package registrations."""
        registry = InvariantRegistry()

        registry.register("package-1", lambda ctx, fail: None)
        registry.register("package-2", lambda ctx, fail: None)
        registry.register("package-3", lambda ctx, fail: None)

        assert registry.registrations == {"package-1", "package-2", "package-3"}

    def test_complex_regex_patterns(self) -> None:
        """Should handle complex regex patterns."""
        registry = InvariantRegistry(
            config=Config(
                package_allowlist=[
                    "^my-.*",
                    ".*-prod$",
                    "^test-(dev|staging)-.*",
                ]
            )
        )

        # These should all be valid
        assert len(registry.package_allowlist) == 3

    def test_installer_with_no_fail_calls(self) -> None:
        """Installer that doesn't call fail() should succeed."""
        registry = InvariantRegistry()

        def installer(ctx, fail):
            # Do some checks but don't fail
            pass

        # Should not raise
        dispose = registry.register("my-package", installer)
        assert "my-package" in registry.registrations
