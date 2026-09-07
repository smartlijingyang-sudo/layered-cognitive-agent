"""Behavioral tests for ``PluginContract.privileges`` (ADR-0199 §3.1 + I-HPC-5).

Covers the fourth contract dimension declared in ADR-0199 §3.1:
``privileges`` is **distinct from** ``provides`` — it represents what
the plugin is **authorized to do** (side effects), not what capability
it advertises. ``PRIVILEGE_PREFIXES`` is the closed set of known
prefixes; unknown prefixes emit a warning rather than hard-failing
(forward-compatible). ``UndeclaredPrivilegeError`` is the typed seam
the harness / guard stack raises when a plugin attempts an effect
whose privilege it has not declared.
"""

from __future__ import annotations

import importlib
import sys
import warnings

import pytest

from lca.contracts.harness.composition.plugin_contract import (
    PRIVILEGE_PREFIXES,
    AuthorityContract,
    CapabilityContract,
    PluginContract,
    UndeclaredPrivilegeError,
    is_plugin_contract_empty,
)

# ---------------------------------------------------------------------------
# Defaults and basic field behaviour
# ---------------------------------------------------------------------------


def test_plugin_contract_privileges_default_empty() -> None:
    """``PluginContract()`` defaults ``privileges`` to an empty tuple.

    Backward compatibility: existing constructors that omit ``privileges``
    must continue to work and report an empty privilege set.
    """
    contract = PluginContract()
    assert contract.privileges == ()


def test_plugin_contract_privileges_set() -> None:
    """Privileges can be declared as a tuple of dotted strings."""
    contract = PluginContract(
        privileges=("journal.append", "network.egress"),
    )
    assert contract.privileges == ("journal.append", "network.egress")


def test_plugin_contract_privileges_frozen() -> None:
    """``PluginContract`` remains ``frozen=True, slots=True`` after P3-01.

    Assigning to ``privileges`` post-construction must raise
    ``FrozenInstanceError`` — the privilege set is part of the contract
    identity and must not mutate at runtime.
    """
    contract = PluginContract(privileges=("journal.append",))
    with pytest.raises((AttributeError, Exception)):
        contract.privileges = ("network.egress",)  # type: ignore[misc]


def test_plugin_contract_privileges_rejects_empty_string() -> None:
    """Empty privilege strings raise :class:`UndeclaredPrivilegeError`."""
    with pytest.raises(UndeclaredPrivilegeError, match="empty strings"):
        PluginContract(privileges=("",))


def test_plugin_contract_privileges_rejects_non_string_entry() -> None:
    """Non-string privilege entries raise :class:`UndeclaredPrivilegeError`."""
    with pytest.raises(UndeclaredPrivilegeError, match="must be str"):
        PluginContract(privileges=("journal.append", 42))  # type: ignore[arg-type]


def test_plugin_contract_privileges_coerces_list_to_tuple() -> None:
    """Passing a list is normalised to a tuple (frozen=True invariant)."""
    contract = PluginContract(privileges=["journal.append", "state.read"])
    assert isinstance(contract.privileges, tuple)
    assert contract.privileges == ("journal.append", "state.read")


# ---------------------------------------------------------------------------
# Closed-set prefix behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prefix",
    [
        "journal.",  # Session.append, durable writes
        "state.",  # Reducer-only state writes (C4)
        "memory.",  # Memory backend read/write
        "tools.",  # Tool invocation (C10 narrow gate)
        "policy.",  # Policy / Gate effects
        "network.",  # Network egress (untrusted-only by default)
        "process.",  # Process spawn (sandbox-gated)
        "fs.",  # Filesystem writes outside the workspace
        "k3.",  # K3 boot / fiber setup
    ],
)
def test_known_privilege_prefixes_accepted(prefix: str) -> None:
    """All 9 closed-set prefixes construct without warning."""
    privilege = f"{prefix}verb"
    # Promote UserWarning to error so any PRIVILEGE_PREFIXES warning fails the test.
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        contract = PluginContract(privileges=(privilege,))
    assert contract.privileges == (privilege,)


def test_unknown_privilege_prefix_emits_warning() -> None:
    """Unknown prefixes emit ``UserWarning`` (forward-compatible, not error)."""
    with pytest.warns(UserWarning, match="PRIVILEGE_PREFIXES"):
        PluginContract(privileges=("custom_namespace.verb",))


def test_privilege_prefixes_constant_complete() -> None:
    """``PRIVILEGE_PREFIXES`` contains exactly the 9 documented prefixes.

    This is the closed-set gate; widening requires an ADR / doctor rule
    update. Adding a prefix here is a deliberate, reviewable action.
    """
    assert (
        frozenset(
            {
                "journal.",
                "state.",
                "memory.",
                "tools.",
                "policy.",
                "network.",
                "process.",
                "fs.",
                "k3.",
            }
        )
        == PRIVILEGE_PREFIXES
    )
    assert len(PRIVILEGE_PREFIXES) == 9


# ---------------------------------------------------------------------------
# Exception class
# ---------------------------------------------------------------------------


def test_undeclared_privilege_error_class_exists() -> None:
    """``UndeclaredPrivilegeError`` is exported from the module."""
    assert UndeclaredPrivilegeError is not None


def test_undeclared_privilege_error_is_value_error() -> None:
    """``UndeclaredPrivilegeError`` subclasses ``ValueError``.

    Per C10 / I-HPC-5 deterministic errors do not retry; being a
    ``ValueError`` keeps that classification intact and allows
    generic ``except ValueError`` callers to keep working.
    """
    assert issubclass(UndeclaredPrivilegeError, ValueError)


def test_undeclared_privilege_error_can_be_raised_with_message() -> None:
    """``UndeclaredPrivilegeError`` accepts and exposes a message."""
    with pytest.raises(UndeclaredPrivilegeError, match="missing privilege"):
        raise UndeclaredPrivilegeError("plugin X is missing privilege Y")


# ---------------------------------------------------------------------------
# Orthogonality vs other dimensions
# ---------------------------------------------------------------------------


def test_privileges_distinct_from_provides() -> None:
    """A plugin may declare the same string in both ``provides`` and ``privileges``.

    Per ADR-0199 §3.1 the two dimensions are orthogonal; identical keys
    in both lists are *not* a contradiction, they are two separate
    statements (``what I advertise`` vs ``what I am authorised to do``).
    """
    contract = PluginContract(
        capabilities=CapabilityContract(provides=("memory.semantic",)),
        privileges=("memory.semantic",),
    )
    assert contract.capabilities.provides == ("memory.semantic",)
    assert contract.privileges == ("memory.semantic",)


def test_privileges_distinct_from_authority_grants() -> None:
    """``privileges`` is a separate field from ``authority.grants``.

    ``AuthorityContract.grants`` describes the gate's grant / approval
    posture; ``privileges`` describes the side-effect authorization.
    Both can be set independently without one implying the other.
    """
    contract = PluginContract(
        authority=AuthorityContract(grants=("network.egress",), risk_level="high"),
        privileges=("journal.append",),
    )
    assert contract.authority.grants == ("network.egress",)
    assert contract.authority.risk_level == "high"
    assert contract.privileges == ("journal.append",)


def test_privileges_orthogonal_to_capabilities() -> None:
    """Setting ``privileges`` does not influence ``CapabilityContract``."""
    privileges = ("journal.append", "state.write")
    capabilities = CapabilityContract(provides=("memory.semantic",))
    contract = PluginContract(
        capabilities=capabilities,
        privileges=privileges,
    )
    assert contract.capabilities.provides == ("memory.semantic",)
    assert contract.capabilities.requires == ()
    assert contract.capabilities.effect_classes == ()
    assert contract.privileges == privileges


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


def test_backward_compat_no_privileges_arg() -> None:
    """Existing callers (no ``privileges`` kwarg) keep working unchanged."""
    contract = PluginContract(
        capabilities=CapabilityContract(provides=("memory.semantic",)),
    )
    assert contract.privileges == ()
    assert is_plugin_contract_empty(contract) is False  # provides still populated


def test_is_plugin_contract_empty_when_only_privileges_set() -> None:
    """``is_plugin_contract_empty`` treats ``privileges`` as a real field:
    a contract whose only non-default value is ``privileges`` is **not**
    empty (the author declared something).
    """
    contract = PluginContract(privileges=("journal.append",))
    assert is_plugin_contract_empty(contract) is False


def test_is_plugin_contract_empty_when_truly_default() -> None:
    """``is_plugin_contract_empty`` still returns True when everything is default."""
    assert is_plugin_contract_empty(PluginContract()) is True


# ---------------------------------------------------------------------------
# Module purity (contracts layer)
# ---------------------------------------------------------------------------


@pytest.mark.subprocess
def test_no_journal_or_session_import() -> None:
    """Module stays contracts-layer clean: no I/O, no journal/session imports.

    Runs in a SUBPROCESS to avoid sys.modules pollution from sibling
    test files that transitively import lca.harness / lca.journal etc.
    """
    import subprocess
    import sys as _sys
    result = subprocess.run(
        [_sys.executable, "-c", """
import sys
import lca.contracts.harness.composition.plugin_contract
forbidden = (
    "lca.harness", "lca.journal", "lca.session", "lca.runtime",
    "lca.plugins", "lca.application", "lca.cognition",
    "lca.infrastructure", "lca.agent",
)
leaked = [
    n for n in sys.modules
    if n.startswith("lca.")
    and any(sub in n for sub in forbidden)
    and n != "lca.contracts.harness.composition.plugin_contract"
]
assert leaked == [], f"plugin_contract pulled: {leaked}"
print("OK")
"""],
        capture_output=True, text=True, check=False, cwd="/home/lichao/layered-cognitive-agent",
    )
    assert result.returncode == 0, f"subprocess failed: {result.stderr}"


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


def test_all_exports_present() -> None:
    """``__all__`` exposes both the new symbols and the existing ones."""
    import lca.contracts.harness.composition.plugin_contract as mod

    assert "PRIVILEGE_PREFIXES" in mod.__all__
    assert "UndeclaredPrivilegeError" in mod.__all__
    # Backward-compat: existing exports remain.
    for name in (
        "PluginContract",
        "PluginIdentity",
        "CapabilityContract",
        "AuthorityContract",
        "is_plugin_contract_empty",
    ):
        assert name in mod.__all__
