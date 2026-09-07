"""External-plugin trust doctor pass (ADR-0199 §5 / §10 Phase 5 + HPC-L7).

Per ADR-0199 §10 Phase 5 + the rubric in
``docs/specs/external-plugin-trust-rubric.md``:

| Privilege prefix   | Required external_kind | Why |
|--------------------|------------------------|-----|
| state.             | inprocess              | C4 Reducer 单写 — only inprocess reducers can write |
| journal.           | inprocess | worker   | journal is inprocess or trusted worker |
| network.           | mcp | sandbox       | network egress via OS boundary |
| process.           | sandbox                | OS-level isolation required |
| fs. (out-of-ws)    | sandbox                | workspace-local writes can be inprocess |
| memory. / tools. / policy. / k3. | any | per plugin choice |

This pass audits :class:`PluginContract.privileges` against the runtime
``external_kind`` decision. Conflicts emit ``DOC-TRUST-001`` findings so
that ``lca-ops doctor profile --ci`` fails closed at the CI gate
(ADR-0199 §5.3) and operators can relocate the plugin via profile
provenance (per the rubric §4).

Architectural rules:
  - Per I-HPC-7: pure pass, no I/O, no K3 boot, no journal writes.
  - Per C8: deterministic iteration order over inputs.
  - Per HPC-L7: complements the untrusted-default-disabled gate by
    catching kind-vs-privilege mismatches that resolve alone cannot see.
"""

from __future__ import annotations

from collections.abc import Iterable

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
)
from lca.contracts.harness.composition.plugin_contract import PluginContract
from lca.contracts.runtime.external_plugin import ExternalPluginKind

_OWNER_ADR: str = "ADR-0199"


# Privilege prefix → required external_kinds.
# "any" is modelled by omitting the prefix (see run() short-circuit).
# Adding a new constraint is a privilege change and needs an ADR.
PRIVILEGE_KIND_REQUIREMENTS: dict[str, frozenset[ExternalPluginKind]] = {
    "state.": frozenset({"inprocess"}),
    "journal.": frozenset({"inprocess", "worker"}),
    "network.": frozenset({"mcp", "sandbox"}),
    "process.": frozenset({"sandbox"}),
}


def _privilege_prefix_in_table(privilege: str) -> str | None:
    """Return the first table key whose prefix ``privilege`` starts with.

    Iterates :data:`PRIVILEGE_KIND_REQUIREMENTS` deterministically
    (Python 3.7+ dict preserves insertion order; the table is built
    in source order in this module). Prefixes not present in the table
    (``memory.``, ``tools.``, ``policy.``, ``k3.``, ``fs.`` workspace-local)
    return ``None`` and signal "any kind is fine".
    """
    for prefix in PRIVILEGE_KIND_REQUIREMENTS:
        if privilege.startswith(prefix):
            return prefix
    return None


class TrustDoctor:
    """Single doctor pass: external_kind vs privileges consistency.

    Per ADR-0199 §10 Phase 5 / P5-04 + HPC-L7. Audits each plugin's
    runtime ``external_kind`` decision against the privilege declarations
    on its :class:`PluginContract`. Conflicts emit ``DOC-TRUST-001``
    findings; the orchestrator (P2-07 ``DoctorFacade``) aggregates them
    into the profile-level :class:`DoctorReport`.
    """

    def run(
        self,
        plugin_contracts: Iterable[PluginContract],
        *,
        external_kind_by_plugin: dict[str, ExternalPluginKind],
    ) -> DoctorReport:
        """Audit each plugin's external_kind against its privilege declarations.

        Args:
          plugin_contracts: the plugin contracts to audit.
          external_kind_by_plugin: maps ``plugin_id -> ExternalPluginKind``;
                                   the runtime decision (operator overrides
                                   the manifest's advisory per the rubric
                                   §4). Plugins absent from the map default
                                   to ``inprocess`` (treat as bundled core).

        Per I-HPC-7: pure pass, no I/O, no journal writes.
        Per C8: deterministic iteration order (consumes inputs in
        supplied order, no sorting); the requirement-table prefix scan
        is deterministic via :data:`PRIVILEGE_KIND_REQUIREMENTS`
        insertion order.
        """
        findings: list[DoctorFinding] = []

        for contract in plugin_contracts:
            plugin_id = contract.identity.id
            kind = external_kind_by_plugin.get(plugin_id, "inprocess")

            for privilege in contract.privileges:
                table_prefix = _privilege_prefix_in_table(privilege)
                if table_prefix is None:
                    # Privilege has no kind requirement — any kind is fine
                    continue

                required_kinds = PRIVILEGE_KIND_REQUIREMENTS[table_prefix]
                if kind not in required_kinds:
                    findings.append(
                        DoctorFinding(
                            code="DOC-TRUST-001",
                            severity="error",
                            owner=_OWNER_ADR,
                            message=(
                                f"plugin {plugin_id!r} has external_kind={kind!r} but "
                                f"privilege {privilege!r} requires one of "
                                f"{sorted(required_kinds)}"
                            ),
                            remediation=(
                                f"Per the trust rubric (external-plugin-trust-rubric.md "
                                f"§2): privilege prefix {table_prefix!r} requires "
                                f"external_kind in {sorted(required_kinds)}. Update "
                                f"the plugin manifest or the operator profile to use "
                                f"a compatible kind."
                            ),
                            plugin_id=plugin_id,
                        )
                    )

        return DoctorReport.from_findings(
            subject="external_trust_audit",
            findings=findings,
        )


__all__ = ("PRIVILEGE_KIND_REQUIREMENTS", "TrustDoctor")
