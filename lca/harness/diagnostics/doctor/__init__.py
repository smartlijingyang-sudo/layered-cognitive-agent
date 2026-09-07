"""Doctor facade pieces (ADR-0199 P2).

Each submodule is a single, testable DoctorPass; the orchestrator (P2-07)
composes them. Per I-HPC-7 none of these passes may have side effects.
"""

from lca.harness.diagnostics.doctor.capability_cardinality import (
    CapabilityCardinalityDoctor,
)
from lca.harness.diagnostics.doctor.compile_dry_run import (
    DoctorCompileError,
    ProfileCompileDryRun,
)
from lca.harness.diagnostics.doctor.facade import DoctorFacade
from lca.harness.diagnostics.doctor.phase_graph import (
    _CLOSED_PHASES,
    PhaseGraphDoctor,
)
from lca.harness.diagnostics.doctor.plugin_shape import PluginShapeDoctor
from lca.harness.diagnostics.doctor.privilege import PrivilegeDoctor
from lca.harness.diagnostics.doctor.resource_pass import ResourceDoctor
from lca.harness.diagnostics.doctor.single_plugin import SinglePluginDoctor
from lca.harness.diagnostics.doctor.trust import (
    PRIVILEGE_KIND_REQUIREMENTS,
    TrustDoctor,
)

__all__ = (
    "PRIVILEGE_KIND_REQUIREMENTS",
    "_CLOSED_PHASES",
    "CapabilityCardinalityDoctor",
    "DoctorCompileError",
    "DoctorFacade",
    "PhaseGraphDoctor",
    "PluginShapeDoctor",
    "PrivilegeDoctor",
    "ProfileCompileDryRun",
    "ResourceDoctor",
    "SinglePluginDoctor",
    "TrustDoctor",
)
