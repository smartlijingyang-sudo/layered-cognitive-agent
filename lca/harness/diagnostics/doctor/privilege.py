"""Privilege doctor pass (ADR-0199 §3.1 and §3.3 #5, I-HPC-5).

Per ADR-0199 §3.1, provides, requires, privileges, and resources are
orthogonal. Per §3.3 #5 and I-HPC-5, an undeclared privilege fails setup.
This pass audits plugin contracts for privilege/effect consistency.

DOC-PRIV-001 (error): effect declared without matching privilege
DOC-PRIV-002 (error): privilege with unknown prefix (closed-set violation)
DOC-PRIV-003 (warning): privilege declared without any effects (orphan)
DOC-PRIV-004 (info): privilege and effect counts match (sanity check)
"""

from __future__ import annotations

from collections.abc import Iterable

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
)
from lca.contracts.harness.composition.plugin_contract import (
    PRIVILEGE_PREFIXES,
    PluginContract,
)

_OWNER_ADR: str = "ADR-0199"


class PrivilegeDoctor:
    """Single doctor pass for privilege/effect consistency (ADR-0199 I-HPC-5)."""

    def run(
        self,
        plugin_contracts: Iterable[PluginContract],
    ) -> DoctorReport:
        """Audit privilege declarations against effects across plugin contracts."""
        findings: list[DoctorFinding] = []
        privilege_set: set[str] = set()
        effects_by_plugin: dict[str | None, list[str]] = {}

        for contract in plugin_contracts:
            plugin_id = contract.identity.id

            for privilege in contract.privileges:
                privilege_set.add(privilege)
                if not any(privilege.startswith(prefix) for prefix in PRIVILEGE_PREFIXES):
                    findings.append(
                        DoctorFinding(
                            code="DOC-PRIV-002",
                            severity="error",
                            owner=_OWNER_ADR,
                            message=(
                                f"plugin {plugin_id!r} declares privilege {privilege!r} "
                                f"with unknown prefix; known prefixes: "
                                f"{sorted(PRIVILEGE_PREFIXES)}"
                            ),
                            remediation=(
                                "Per ADR-0199 §3.1 privileges use "
                                "'domain.verb[.scope]' format. Add a new prefix "
                                "via ADR; do not introduce arbitrary short names."
                            ),
                            plugin_id=plugin_id,
                        )
                    )

            effects = contract.capabilities.effect_classes
            effects_by_plugin[plugin_id] = list(effects)
            if contract.privileges and not effects:
                findings.append(
                    DoctorFinding(
                        code="DOC-PRIV-003",
                        severity="warning",
                        owner=_OWNER_ADR,
                        message=(
                            f"plugin {plugin_id!r} declares "
                            f"{len(contract.privileges)} privileges but no effects; "
                            "privileges without effects are orphans"
                        ),
                        remediation=(
                            "Either declare matching effects, or remove the "
                            "privilege if it is no longer needed. Orphan privileges "
                            "bloat the trust envelope without granting capability."
                        ),
                        plugin_id=plugin_id,
                    )
                )

            for effect in effects:
                prefix = effect.split(".", 1)[0] + "."
                if not any(privilege.startswith(prefix) for privilege in contract.privileges):
                    findings.append(
                        DoctorFinding(
                            code="DOC-PRIV-001",
                            severity="error",
                            owner=_OWNER_ADR,
                            message=(
                                f"plugin {plugin_id!r} declares effect {effect!r} "
                                f"but has no matching privilege (no privilege starts "
                                f"with {prefix!r})"
                            ),
                            remediation=(
                                "Per ADR-0199 §3.3 #5 and I-HPC-5 an undeclared "
                                "privilege fails setup. Add a privilege starting "
                                f"with the same prefix as the effect "
                                f"(e.g. {effect!r} → {prefix}*)."
                            ),
                            plugin_id=plugin_id,
                        )
                    )

        if privilege_set and not findings:
            findings.append(
                DoctorFinding(
                    code="DOC-PRIV-004",
                    severity="info",
                    owner=_OWNER_ADR,
                    message=(
                        f"audited {len(privilege_set)} unique privileges across "
                        f"{len(effects_by_plugin)} plugin contracts; no inconsistencies"
                    ),
                    remediation="No remediation is required; privileges and effects are consistent.",
                    plugin_id=None,
                )
            )

        return DoctorReport.from_findings(
            subject="privilege_audit",
            findings=findings,
        )


__all__ = ("PrivilegeDoctor",)
