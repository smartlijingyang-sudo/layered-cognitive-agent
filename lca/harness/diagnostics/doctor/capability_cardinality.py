"""Capability cardinality doctor pass (ADR-0199 §2.3 / P2-05).

Per ADR-0199 §2.3 Unified Discovery Protocol: each capability key may
have AT MOST ONE active provider. Multiple providers for the same key
is a SSOT violation; the doctor reports each duplicate as DOC-CAP-001.

This pass reads a provided plugin-contract set and emits findings
without modifying anything. Per I-HPC-7: no K3 boot, no journal writes,
no network I/O, no subprocess calls.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from lca.contracts.diagnostics.doctor import DoctorReport

if TYPE_CHECKING:
    from lca.contracts.harness.composition.plugin_contract import PluginContract


_OWNER_ADR: str = "ADR-0199"


class CapabilityCardinalityDoctor:
    """Single doctor pass: capability duplicates → DoctorReport (ADR-0199 P2-05).

    Per ADR-0199 §2.3 each capability key may have AT MOST ONE active
    provider. This pass audits a resolved profile's plugin contracts and
    emits one ``DOC-CAP-001`` finding per duplicated capability, listing
    every contributing ``plugin_id`` in the message.

    The pass is deterministic (C8) and read-only (I-HPC-7): it never
    touches the filesystem, the journal, or any boot state.
    """

    def __init__(self, *, profile_path: str | Path | None = None) -> None:
        # profile_path is accepted for facade-shape parity; this pass
        # reads from a provided plugin set rather than the filesystem.
        self._profile_path = Path(profile_path) if profile_path else None

    def run(
        self,
        plugin_contracts: Iterable[PluginContract],
    ) -> DoctorReport:
        """Audit capability duplicates across plugin contracts.

        Each ``contract.capabilities.provides`` is a tuple of capability
        keys. If the same key appears in multiple contracts, emit one
        ``DOC-CAP-001`` finding per duplicate (with all plugin_ids listed
        in the message).
        """
        from lca.contracts.diagnostics.doctor import DoctorFinding

        subject = str(self._profile_path) if self._profile_path else "capability_cardinality"
        findings: list[DoctorFinding] = []

        # capability_key -> list of plugin_ids (uses identity.id per
        # the canonical PluginContract shape, not a hypothetical
        # contract.plugin_id attribute).
        owners: dict[str, list[str]] = {}
        for contract in plugin_contracts:
            plugin_id = contract.identity.id
            for cap in contract.capabilities.provides:
                owners.setdefault(cap, []).append(plugin_id)

        # Find duplicates — sorted for C8 determinism.
        for cap, plugin_ids in sorted(owners.items()):
            if len(plugin_ids) > 1:
                findings.append(
                    DoctorFinding(
                        code="DOC-CAP-001",
                        severity="error",
                        owner=_OWNER_ADR,
                        message=(
                            f"capability {cap!r} has {len(plugin_ids)} active providers: "
                            f"{', '.join(sorted(plugin_ids))}"
                        ),
                        remediation=(
                            "Per ADR-0199 §2.3 each capability key must have at most one "
                            "active provider. Use Manifest.replaces to declare which plugin "
                            "supersedes the others, or disable one via profile."
                        ),
                        plugin_id=None,
                        plan_ref=None,
                    )
                )

        return DoctorReport.from_findings(subject, findings)


__all__ = ("CapabilityCardinalityDoctor",)
