"""Resource orphan doctor pass (ADR-0199 §5 / P4-07 + I-HPC-6).

Per ADR-0199 §3.1 + I-HPC-6: resources are content, not executables.
A "orphan" resource is one declared in a plugin contract but with no
provider that can resolve it. Orphan resources bloat the registry
without serving any purpose.

This pass audits a ResourceRegistry and emits:

  DOC-RES-001 (warning): resource declared but no provider is registered
  DOC-RES-002 (info): resource resolution graph is empty (no providers)

The pass is PURE: no I/O, no K3 boot, no journal writes. Per I-HPC-7.
"""

from __future__ import annotations

from collections.abc import Iterable

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
)
from lca.harness.composition.resource_registry import ResourceRegistry

_OWNER_ADR: str = "ADR-0199"


class ResourceDoctor:
    """Single doctor pass: orphan-resource audit (ADR-0199 P4-07)."""

    def __init__(
        self,
        *,
        available_providers: Iterable[str] = (),
    ) -> None:
        # The set of provider names that can resolve resources.
        # In real wiring this would be the names of SkillProvider /
        # prompt / role providers registered in the harness.
        self._providers = frozenset(available_providers)

    def run(self, registry: ResourceRegistry) -> DoctorReport:
        """Audit the registry for orphan resources.

        A resource is "orphan" when its kind (skill / prompt / role) has
        no matching provider in self._providers. This is a coarse check —
        a finer-grained check would map ResourceId.namespace → provider;
        the coarse check is sufficient for P4-07.
        """
        findings: list[DoctorFinding] = []
        subject = f"resource_registry({len(registry)} resources)"

        if not self._providers:
            # No providers at all — every resource is orphan
            findings.append(
                DoctorFinding(
                    code="DOC-RES-002",
                    severity="info",
                    owner=_OWNER_ADR,
                    message="no providers available; cannot resolve any resource",
                    remediation=(
                        "Register at least one provider (SkillProvider / prompt / "
                        "role) before relying on resources."
                    ),
                    plugin_id=None,
                )
            )

        # Each resource kind maps to a provider prefix
        kind_to_provider_prefix: dict[str, str] = {
            "skill": "skill",
            "prompt": "prompt",
            "role": "role",
        }

        for rid in registry.resources:
            kind = rid.kind
            prefix = kind_to_provider_prefix.get(kind, kind)
            has_provider = any(p.startswith(prefix) for p in self._providers)
            if not has_provider:
                findings.append(
                    DoctorFinding(
                        code="DOC-RES-001",
                        severity="warning",
                        owner=_OWNER_ADR,
                        message=(
                            f"resource {rid.to_ref()!r} is orphan: no provider "
                            f"matching prefix {prefix!r} is registered"
                        ),
                        remediation=(
                            "Either register a provider that can serve this resource "
                            f"(provider name must start with {prefix!r}), or remove "
                            "the orphan resource from its declaring plugin's contract."
                        ),
                        plugin_id=None,
                    )
                )

        return DoctorReport.from_findings(subject, findings)


__all__ = ("ResourceDoctor",)
