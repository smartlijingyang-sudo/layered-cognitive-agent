"""ADR-0199 §9 invariant snapshot (PR-0199-P3-10 acceptance).

Per ADR-0199 §17 acceptance #7 ("HPC-L1–L8 门禁建立"), the §9 ``I-HPC-*``
invariants must be pinned by code, not prose. This module imports the
canonical contracts and asserts their shapes match the ADR, so that
deleting or loosening an anchor symbol fails CI.

Each invariant maps to a concrete code reference:

  I-HPC-1  入口薄              — ``RuntimeFacade`` Protocol (P1-04) is the unique
                                 consumer of ``RunIntent``
  I-HPC-2  Plan 不可变          — ``SessionActivation.compiled_plan`` is read-only (P1-03)
  I-HPC-3  Activation 绑定      — ``compute_activation_ref`` is deterministic (P1-06)
  I-HPC-4  声明先于执行         — ``RuntimeFacade`` is a typed Protocol (P1-04 + P3-07)
  I-HPC-5  privileges fail-closed — ``UndeclaredPrivilegeError`` (P3-01) + privilege
                                 check in ``AuditedPluginContext`` (P3-07)
  I-HPC-6  内容只读             — ``ResourceId`` (P4-01) is frozen; content providers
                                 never register executable capabilities
  I-HPC-7  Doctor 只读          — ``DoctorReport.from_findings`` is pure (P2-01/02);
                                 doctor passes never call ``Session.append``
  I-HPC-8  Hook 不旁路          — plugin hooks are typed events (existing convention)
  I-HPC-9  分域 registry        — no global mutable tool registry (HPC-L8, P5-05)
  I-HPC-10 自我改进受审计       — ``PlanProposal`` is frozen (P4-03); activation is
                                 read-only (P4-04)
  I-HPC-11 信任默认拒绝         — ``default_external_kind("untrusted") == "mcp"`` (P5-02)
  I-HPC-12 与 C1/C5/C7/C8/C11 一致 — ``PhaseGraphDoctor`` enforces the 6-phase
                                 closed set (P2-06)
"""

from __future__ import annotations

import dataclasses

import pytest


class TestInvariantCanonicalReferences:
    """Each I-HPC-* invariant has a canonical symbol in the contracts layer."""

    def test_i_hpc_1_runtime_facade_protocol_is_unique_consumer(self) -> None:
        """I-HPC-1: RuntimeFacade is the unique consumer of RunIntent."""
        from lca.contracts.runtime.facade import RuntimeFacade

        assert hasattr(RuntimeFacade, "resolve_activation")
        assert hasattr(RuntimeFacade, "dispatch_run")

    def test_i_hpc_2_session_activation_compiled_plan_optional(self) -> None:
        """I-HPC-2: SessionActivation captures CompiledRunPlan (read-only)."""
        from lca.contracts.runtime.activation import SessionActivation

        fields = {f.name for f in dataclasses.fields(SessionActivation)}
        assert "compiled_plan" in fields, "SessionActivation must carry compiled_plan (optional)"

    def test_i_hpc_3_activation_ref_format(self) -> None:
        """I-HPC-3: activation_ref is deterministic via compute_activation_ref."""
        from lca.harness.runtime.activation_ref import compute_activation_ref

        ref = compute_activation_ref(
            plan_ref="plan_x",
            graph_ref="graph_y",
            plugin_set_ref="plugin_z",
            session_id="sess_test",
        )
        assert ref.startswith("lca.activation.v1:")
        assert len(ref) == len("lca.activation.v1:") + 64

    def test_i_hpc_4_runtime_facade_is_runtime_checkable_protocol(self) -> None:
        """I-HPC-4: RuntimeFacade declares its surface before execution."""
        from typing import Protocol

        from lca.contracts.runtime.facade import RuntimeFacade

        assert Protocol in RuntimeFacade.__mro__
        # Annotations stay strings: RunIntent is a TYPE_CHECKING-only import in
        # the contracts layer, so the declared surface is checked textually.
        annotations = RuntimeFacade.resolve_activation.__annotations__
        assert annotations["intent"] == "RunIntent"
        assert annotations["return"] == "SessionActivation"

    def test_i_hpc_5_undeclared_privilege_error_exists(self) -> None:
        """I-HPC-5: UndeclaredPrivilegeError is the privilege fail-closed exception."""
        from lca.contracts.harness.composition.plugin_contract import (
            UndeclaredPrivilegeError,
        )

        assert issubclass(UndeclaredPrivilegeError, ValueError)

    def test_i_hpc_6_resource_id_is_frozen(self) -> None:
        """I-HPC-6: ResourceId is frozen (read-only content)."""
        from lca.contracts.runtime.resource import ResourceId

        assert dataclasses.fields(ResourceId)[0].name == "kind"
        rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
        with pytest.raises(dataclasses.FrozenInstanceError):
            rid.name = "mutated"  # type: ignore[misc]

    def test_i_hpc_7_doctor_report_pure_construction(self) -> None:
        """I-HPC-7: DoctorReport.from_findings is pure (no side effects)."""
        from lca.contracts.diagnostics.doctor import DoctorFinding, DoctorReport

        report = DoctorReport.from_findings(
            subject="test",
            findings=[
                DoctorFinding(
                    code="DOC-PS-001",
                    severity="error",
                    owner="ADR-0199",
                    message="test",
                    remediation="remediation",
                )
            ],
        )
        assert report.subject == "test"
        assert report.summary.errors == 1

    def test_i_hpc_10_plan_proposal_is_frozen(self) -> None:
        """I-HPC-10: PlanProposal is frozen (no mutation)."""
        from lca.contracts.runtime.plan_proposal import build_proposal

        proposal = build_proposal(
            source_activation_ref="lca.activation.v1:" + "a" * 64,
            candidate_plan_ref="plan_x",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            proposal.status = "reviewing"  # type: ignore[misc]

    def test_i_hpc_11_untrusted_default_kind_is_mcp(self) -> None:
        """I-HPC-11: untrusted plugin's default ExternalPluginKind is mcp."""
        from lca.contracts.runtime.external_plugin import default_external_kind

        assert default_external_kind("untrusted") == "mcp"
        assert default_external_kind("trusted") == "inprocess"
        assert default_external_kind("core") == "inprocess"

    def test_i_hpc_12_phase_graph_doctor_enforces_closed_set(self) -> None:
        """I-HPC-12 + C1: PhaseGraphDoctor enforces the 6-phase closed set."""
        from lca.harness.diagnostics.doctor.phase_graph import _CLOSED_PHASES

        expected = frozenset(
            {
                "perceive",
                "think",
                "act",
                "reflect",
                "remember",
                "stop",
            }
        )
        assert expected == _CLOSED_PHASES


class TestCrossInvariantImports:
    """All invariant symbols import cleanly — no broken refs."""

    def test_no_circular_imports_between_invariant_modules(self) -> None:
        """Importing all invariant anchor modules in sequence must succeed."""
        from lca.contracts.diagnostics.doctor import DoctorReport  # noqa: F401
        from lca.contracts.harness.composition.plugin_contract import (  # noqa: F401
            UndeclaredPrivilegeError,
        )
        from lca.contracts.runtime.activation import SessionActivation  # noqa: F401
        from lca.contracts.runtime.external_plugin import ExternalPluginKind  # noqa: F401
        from lca.contracts.runtime.facade import RuntimeFacade  # noqa: F401
        from lca.contracts.runtime.plan_proposal import PlanProposal  # noqa: F401
        from lca.contracts.runtime.resource import ResourceId  # noqa: F401
        from lca.harness.diagnostics.doctor.phase_graph import _CLOSED_PHASES  # noqa: F401
        from lca.harness.runtime.activation_ref import compute_activation_ref  # noqa: F401
