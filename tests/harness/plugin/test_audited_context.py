"""Tests for ``lca.harness.plugin.audited_context`` (PR-0199-P3-07).

Per ADR-0199 §3.3 #5 and I-HPC-5: ``check_privilege`` is the single seam
where plugin setup() validates privilege use before invoking a privileged
action. Undeclared privilege triggers fail-closed via
``UndeclaredPrivilegeError``.
"""

from __future__ import annotations

import contextlib
import inspect

import pytest

from lca.contracts.harness.composition.plugin_contract import (
    PluginContract,
    PluginIdentity,
    UndeclaredPrivilegeError,
)
from lca.harness.plugin.audited_context import (
    PrivilegeCheckError,
    audit_setup_privileges,
    check_privilege,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _contract(
    *,
    privileges: tuple[str, ...] = (),
    version: str = "0.0.0",
    pid: str = "test.plugin",
) -> PluginContract:
    """Build a minimal PluginContract with only the relevant fields set."""
    return PluginContract(
        identity=PluginIdentity(id=pid, version=version, owner="tests"),
        privileges=privileges,
    )


# ---------------------------------------------------------------------------
# check_privilege — happy paths
# ---------------------------------------------------------------------------


def test_check_privilege_passes_for_declared_privilege() -> None:
    """A privilege present in PluginContract.privileges returns without raising."""
    contract = _contract(privileges=("journal.append",))
    check_privilege("test.plugin", "journal.append", contract=contract)


def test_check_privilege_with_contract_by_id_lookup() -> None:
    """Lookup-table path: contract_by_id resolves plugin_id to a contract."""
    contracts = {
        "writer": _contract(privileges=("journal.append", "memory.write"), pid="writer"),
    }
    check_privilege("writer", "journal.append", contracts)
    check_privilege("writer", "memory.write", contracts)


def test_check_privilege_with_direct_contract() -> None:
    """Direct contract path: caller already holds the PluginContract."""
    contract = _contract(privileges=("tools.invoke",), pid="tool.plugin")
    check_privilege("tool.plugin", "tools.invoke", contract=contract)


# ---------------------------------------------------------------------------
# check_privilege — failure paths
# ---------------------------------------------------------------------------


def test_check_privilege_raises_undeclared_for_missing_privilege() -> None:
    """An undeclared privilege raises UndeclaredPrivilegeError."""
    contract = _contract(privileges=("journal.append",))
    with pytest.raises(UndeclaredPrivilegeError) as excinfo:
        check_privilege("test.plugin", "network.egress", contract=contract)
    assert "network.egress" in str(excinfo.value)
    assert "test.plugin" in str(excinfo.value)


def test_check_privilege_raises_when_both_lookups_missing() -> None:
    """Calling with neither contract_by_id nor contract raises PrivilegeCheckError."""
    with pytest.raises(PrivilegeCheckError, match="either contract_by_id or contract"):
        check_privilege("any.plugin", "journal.append")


def test_check_privilege_raises_when_plugin_id_not_in_registry() -> None:
    """plugin_id absent from contract_by_id raises UndeclaredPrivilegeError."""
    contracts = {"known": _contract(privileges=("journal.append",), pid="known")}
    with pytest.raises(UndeclaredPrivilegeError) as excinfo:
        check_privilege("unknown", "journal.append", contracts)
    assert "unknown" in str(excinfo.value)
    assert "not in the contract registry" in str(excinfo.value)


def test_check_privilege_raises_for_empty_privileges_contract() -> None:
    """Empty declared privileges still produce the documented 'Declared privileges: []' phrase."""
    contract = _contract(privileges=())
    with pytest.raises(UndeclaredPrivilegeError) as excinfo:
        check_privilege("empty.plugin", "journal.append", contract=contract)
    assert "Declared privileges: []" in str(excinfo.value)


# ---------------------------------------------------------------------------
# audit_setup_privileges
# ---------------------------------------------------------------------------


def test_audit_setup_privileges_returns_empty_when_all_declared() -> None:
    """All setup-declared privileges are in contract → empty audit tuple."""
    contract = _contract(privileges=("journal.append", "memory.read"))
    missing = audit_setup_privileges("writer.setup", contract, ("journal.append", "memory.read"))
    assert missing == ()


def test_audit_setup_privileges_returns_missing_only() -> None:
    """Only the privileges NOT in the contract are returned as missing."""
    contract = _contract(privileges=("journal.append",))
    missing = audit_setup_privileges(
        "writer.setup", contract, ("journal.append", "network.egress", "memory.read")
    )
    assert missing == ("network.egress", "memory.read")


def test_audit_setup_privileges_preserves_input_order() -> None:
    """Returned missing tuple preserves setup input order (C8 determinism)."""
    contract = _contract(privileges=())
    missing = audit_setup_privileges("writer.setup", contract, ("c", "b", "a", "d", "b"))
    # Input order is preserved; duplicates are NOT collapsed (filter, not dedup).
    assert missing == ("c", "b", "a", "d", "b")


def test_audit_setup_privileges_filters_declared_ones() -> None:
    """Privileges present in contract.privileges are filtered out."""
    contract = _contract(privileges=("journal.append", "memory.read"))
    missing = audit_setup_privileges(
        "writer.setup",
        contract,
        ("journal.append", "network.egress", "memory.read", "tools.invoke"),
    )
    assert missing == ("network.egress", "tools.invoke")


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


def test_privilege_check_error_is_runtime_error() -> None:
    """PrivilegeCheckError subclasses RuntimeError (operational failures)."""
    assert issubclass(PrivilegeCheckError, RuntimeError)


def test_undeclared_privilege_error_is_value_error() -> None:
    """UndeclaredPrivilegeError subclasses ValueError (contract miss = bad input)."""
    assert issubclass(UndeclaredPrivilegeError, ValueError)


# ---------------------------------------------------------------------------
# Purity / no-I-O
# ---------------------------------------------------------------------------


def test_no_io_imports() -> None:
    """Module exposes only pure functions and dataclass-level types — no I/O imports."""
    from lca.harness.plugin import audited_context

    # No pathlib / os / io / asyncio / urllib / requests / httpx / socket modules.
    forbidden = {"os", "sys", "io", "pathlib", "asyncio", "urllib", "requests", "httpx", "socket"}
    src = inspect.getsource(audited_context)
    for name in forbidden:
        assert f"import {name}" not in src and f"from {name}" not in src, (
            f"audited_context imports I/O module {name!r}"
        )


def test_does_not_mutate_contract_privileges() -> None:
    """Calling check_privilege does not mutate the input contract (purity check)."""
    privileges = ("journal.append",)
    contract = _contract(privileges=privileges)
    snapshot = contract.privileges
    # Trigger a successful call.
    check_privilege("test.plugin", "journal.append", contract=contract)
    assert contract.privileges == snapshot
    assert contract.privileges == privileges

    # Trigger a failed call.
    with contextlib.suppress(UndeclaredPrivilegeError):
        check_privilege("test.plugin", "network.egress", contract=contract)
    assert contract.privileges == snapshot
