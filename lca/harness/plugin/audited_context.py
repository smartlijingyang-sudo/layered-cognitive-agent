"""AuditedPluginContext — privilege fail-closed wrapper (ADR-0199 §3.3 / P3-07).

Per AGENTS.md §3 invariant C5 / I-HPC-5: setup() may only call Manifest-
declared provide/require/register/emit, AND any privilege use must be
declared in PluginContract.privileges.

This module provides ``check_privilege()`` — the single seam where
plugin setup() must validate privilege use before invoking a privileged
action. Per ADR-0199 §3.3 #5: undeclared privilege fails setup
(UndeclaredPrivilegeError).

The wrapper does NOT replace the existing PluginContext (from
``lca.harness.plugin_api``); it sits alongside it. Plugins that need
privilege-aware operations call ``check_privilege(plugin_id, privilege)``
from their setup() before doing the privileged work.
"""

from __future__ import annotations

from lca.contracts.harness.composition.plugin_contract import (
    PluginContract,
    UndeclaredPrivilegeError,
)


class PrivilegeCheckError(RuntimeError):
    """Raised at runtime when check_privilege is invoked for an unknown plugin."""


def check_privilege(
    plugin_id: str,
    privilege: str,
    contract_by_id: dict[str, PluginContract] | None = None,
    *,
    contract: PluginContract | None = None,
) -> None:
    """Validate that ``plugin_id`` has ``privilege`` declared in its contract.

    Per ADR-0199 §3.3 #5 and I-HPC-5: setup() must call this BEFORE any
    privileged action. If the privilege is not declared, raises
    UndeclaredPrivilegeError.

    Args:
      plugin_id: the id of the plugin attempting the privilege
      privilege: the privilege string (e.g. ``journal.append``)
      contract_by_id: optional lookup table; pass ``None`` to use ``contract`` directly
      contract: optional single contract; use this when the caller already has it

    One of ``contract_by_id`` or ``contract`` must be provided.

    Per C8: pure function (modulo the raise on miss).
    """
    if contract is None and contract_by_id is None:
        raise PrivilegeCheckError("check_privilege requires either contract_by_id or contract")

    if contract is None:
        # contract_by_id is guaranteed non-None by the prior guard.
        assert contract_by_id is not None  # noqa: S101 — defensive assertion
        if plugin_id not in contract_by_id:
            raise UndeclaredPrivilegeError(
                f"plugin {plugin_id!r} is not in the contract registry; cannot "
                f"validate privilege {privilege!r}"
            )
        contract = contract_by_id[plugin_id]

    # Validate privilege is declared
    if privilege not in contract.privileges:
        raise UndeclaredPrivilegeError(
            f"plugin {plugin_id!r} (version={contract.identity.version!r}) attempted "
            f"privilege {privilege!r} not declared in its contract. "
            f"Declared privileges: {sorted(contract.privileges)}. "
            f"Per ADR-0199 §3.3 #5 setup() must declare all privileges used."
        )


def audit_setup_privileges(
    setup_fn_name: str,
    plugin_contract: PluginContract,
    declared_privileges_in_setup: tuple[str, ...],
) -> tuple[str, ...]:
    """Audit a setup() function's privilege declarations.

    Convenience wrapper: returns the SET of declared privileges that are
    NOT in the contract.privileges tuple. Empty tuple = clean audit.

    Args:
      setup_fn_name: human-readable name (for error messages)
      plugin_contract: the plugin's contract
      declared_privileges_in_setup: privileges that setup() declares it uses

    Returns:
      tuple of (privilege_string,) for each privilege declared in setup()
      that is NOT in plugin_contract.privileges. Empty tuple = clean.
    """
    contract_set = set(plugin_contract.privileges)
    return tuple(p for p in declared_privileges_in_setup if p not in contract_set)


__all__ = (
    "PrivilegeCheckError",
    "audit_setup_privileges",
    "check_privilege",
)
