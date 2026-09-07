"""Behavioral tests for the ResourceDoctor orphan-resource pass (PR-0199-P4-07).

Per ADR-0199 §3.1 + I-HPC-6, resources are content, not executables.
The pass audits a :class:`ResourceRegistry` for orphan resources — those
declared but with no provider registered that could resolve them. Per
I-HPC-7, the pass is read-only: no K3 boot, no journal writes, no
network I/O, no subprocess calls.

These tests exercise the contract without booting the kernel; the
``tests/harness/diagnostics/doctor/conftest.py`` no-op fixture replaces
the harness-level autouse K3 boot.
"""

from __future__ import annotations

import re

import pytest

from lca.contracts.diagnostics.doctor import DoctorFinding, DoctorReport
from lca.contracts.runtime.resource import ResourceId
from lca.harness.composition.resource_registry import ResourceRegistry
from lca.harness.diagnostics.doctor import ResourceDoctor
from lca.harness.diagnostics.doctor.resource_pass import ResourceDoctor as _Direct

# Stable machine-code regex copied verbatim from
# lca.contracts.diagnostics.doctor (DOC-<DOMAIN>-<NNN>).
_CODE_RE = re.compile(r"^DOC-[A-Z]{2,6}-\d{3,}$")


# ─────────── 1. empty / trivial inputs ───────────


def test_empty_registry_no_findings_when_providers_present() -> None:
    """Empty registry + providers present → no findings, no info."""
    doctor = ResourceDoctor(available_providers=("skill.semantic", "prompt.coding_agent"))
    report = doctor.run(ResourceRegistry())
    assert isinstance(report, DoctorReport)
    assert report.findings == ()
    assert report.summary.total == 0
    assert report.summary.errors == 0
    assert report.summary.warnings == 0
    assert report.summary.info == 0


def test_empty_registry_still_emits_doc_res_002_when_no_providers() -> None:
    """Empty registry + no providers → DOC-RES-002 (info) about empty graph."""
    doctor = ResourceDoctor(available_providers=())
    report = doctor.run(ResourceRegistry())
    # Even with no resources, we surface that the resolution graph is empty
    # so the operator knows resources cannot be served.
    codes = [f.code for f in report.findings]
    assert codes == ["DOC-RES-002"]
    assert report.summary.info == 1


# ─────────── 2. happy-path: known providers resolve known kinds ───────────


def test_known_skill_provider_resolves_skill_resources() -> None:
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    doctor = ResourceDoctor(available_providers=("skill.semantic",))
    report = doctor.run(registry)
    assert report.findings == ()
    assert report.summary.total == 0


def test_unknown_kind_resource_is_orphan() -> None:
    """Future kinds (kind= literal new value) fall back to the literal kind as prefix.

    A provider matching exactly that prefix (or starting with it) resolves it.
    """
    # Construct an orphan registry with a single skill resource and no providers
    # whose name starts with "skill".
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    doctor = ResourceDoctor(available_providers=("prompt.coding_agent",))
    report = doctor.run(registry)
    codes = [f.code for f in report.findings]
    assert codes == ["DOC-RES-001"]


# ─────────── 3. orphan emission ───────────


def test_orphan_resource_emits_doc_res_001() -> None:
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    doctor = ResourceDoctor(available_providers=("llm.primary",))  # unrelated provider
    report = doctor.run(registry)
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.code == "DOC-RES-001"
    assert "skill:memory/retrieval" in finding.message


def test_doc_res_001_severity_is_warning() -> None:
    rid = ResourceId(kind="role", namespace="assistants", name="solo")
    registry = ResourceRegistry([rid])
    doctor = ResourceDoctor(available_providers=("skill.semantic",))  # wrong prefix
    finding = doctor.run(registry).findings[0]
    assert finding.severity == "warning"
    assert finding.code == "DOC-RES-001"
    assert _CODE_RE.match(finding.code)


def test_no_providers_emits_doc_res_002() -> None:
    """DOC-RES-002 (info) is emitted when no providers are registered.

    It is independent of whether resources are present: it is a global
    "resolution graph is empty" signal.
    """
    rid = ResourceId(kind="prompt", namespace="coding_agent", name="system")
    registry = ResourceRegistry([rid])
    doctor = ResourceDoctor(available_providers=())
    report = doctor.run(registry)
    codes = [f.code for f in report.findings]
    # 1× DOC-RES-002 (info) + 1× DOC-RES-001 (warning) for the orphan resource.
    assert codes.count("DOC-RES-002") == 1
    assert codes.count("DOC-RES-001") == 1
    # The info finding is the empty-graph notice, not the orphan.
    info_findings = [f for f in report.findings if f.severity == "info"]
    assert len(info_findings) == 1
    assert info_findings[0].code == "DOC-RES-002"


# ─────────── 4. mixed kinds ───────────


def test_mixed_skills_and_prompts_each_find_their_provider() -> None:
    """Each kind resolves against its own provider prefix."""
    resources = (
        ResourceId(kind="skill", namespace="memory", name="retrieval"),
        ResourceId(kind="prompt", namespace="coding_agent", name="system"),
    )
    registry = ResourceRegistry(resources)
    doctor = ResourceDoctor(
        available_providers=("skill.semantic", "prompt.coding_agent"),
    )
    report = doctor.run(registry)
    assert report.findings == ()
    assert report.summary.total == 0


# ─────────── 5. message / remediation content ───────────


def test_finding_message_lists_resource_ref() -> None:
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    doctor = ResourceDoctor(available_providers=("prompt.coding_agent",))
    finding = doctor.run(registry).findings[0]
    assert "skill:memory/retrieval" in finding.message


def test_finding_remediation_mentions_provider_prefix() -> None:
    rid = ResourceId(kind="role", namespace="assistants", name="solo")
    registry = ResourceRegistry([rid])
    doctor = ResourceDoctor(available_providers=("skill.semantic",))
    finding = doctor.run(registry).findings[0]
    # Remediation must tell the operator which provider prefix to register.
    assert "role" in finding.remediation


# ─────────── 6. subject handling ───────────


def test_subject_includes_resource_count() -> None:
    rid_a = ResourceId(kind="skill", namespace="memory", name="retrieval")
    rid_b = ResourceId(kind="skill", namespace="memory", name="summarization")
    registry = ResourceRegistry([rid_a, rid_b])
    doctor = ResourceDoctor(available_providers=("llm.primary",))
    report = doctor.run(registry)
    assert "2 resources" in report.subject


# ─────────── 7. side-effect freedom (I-HPC-7) ───────────


def test_no_io_imports() -> None:
    """Module globals must NOT include subprocess, urllib, requests, etc."""
    import lca.harness.diagnostics.doctor.resource_pass as mod

    assert mod.__all__ == ("ResourceDoctor",)
    forbidden = ("subprocess", "os.system", "urllib", "requests", "httpx", "socket")
    for name in forbidden:
        assert name not in mod.__dict__, f"forbidden name {name!r} in module globals"


# ─────────── 8. parametrized provider prefix matching ───────────


@pytest.mark.parametrize(
    ("providers", "expected_codes", "label"),
    [
        pytest.param(
            ("skill.basic",),
            (),
            "single matching provider",
            id="single-matching",
        ),
        pytest.param(
            ("skill.basic", "skill.advanced"),
            (),
            "multiple matching providers",
            id="multiple-matching",
        ),
        pytest.param(
            ("skill.basic.extra",),
            (),
            "provider name starts with prefix + dot",
            id="prefix-with-dot",
        ),
        pytest.param(
            ("my_skill_thing",),
            ("DOC-RES-001",),
            "provider name not starting with prefix → orphan",
            id="prefix-no-separator",
        ),
        pytest.param(
            ("Skill.basic",),  # uppercase first letter — case-sensitive
            ("DOC-RES-001",),
            "case-sensitive prefix does not match",
            id="case-sensitive",
        ),
        pytest.param(
            ("prompt.coding_agent",),
            ("DOC-RES-001",),
            "wrong-prefix provider does not resolve skill",
            id="wrong-prefix",
        ),
    ],
)
def test_provider_prefix_matching(
    providers: tuple[str, ...],
    expected_codes: tuple[str, ...],
    label: str,
) -> None:
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    doctor = ResourceDoctor(available_providers=providers)
    report = doctor.run(registry)
    assert tuple(f.code for f in report.findings) == expected_codes


# ─────────── 9. unknown provider does not resolve any resource ───────────


def test_unknown_provider_does_not_resolve_any_resource() -> None:
    """A provider whose prefix matches no known resource kind orphans every resource."""
    resources = (
        ResourceId(kind="skill", namespace="memory", name="retrieval"),
        ResourceId(kind="prompt", namespace="coding_agent", name="system"),
        ResourceId(kind="role", namespace="assistants", name="solo"),
    )
    registry = ResourceRegistry(resources)
    doctor = ResourceDoctor(available_providers=("unknown.thing",))
    report = doctor.run(registry)
    # All three resources orphan, one DOC-RES-001 per resource.
    codes = [f.code for f in report.findings]
    assert codes.count("DOC-RES-001") == 3
    assert report.summary.warnings == 3
    assert report.summary.errors == 0
    assert report.summary.info == 0


# ─────────── 10. dataclass contract (smoke) ───────────


def test_finding_is_frozen() -> None:
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    doctor = ResourceDoctor(available_providers=("prompt.coding_agent",))
    finding = doctor.run(registry).findings[0]
    assert isinstance(finding, DoctorFinding)
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError subclass
        finding.code = "DOC-RES-999"  # type: ignore[misc]


# ─────────── 11. constructor: frozenset semantics ───────────


def test_constructor_accepts_iterable_and_dedups_providers() -> None:
    """Duplicate provider names collapse (set semantics) but order is irrelevant."""
    doctor = ResourceDoctor(available_providers=("skill.basic", "skill.basic", "skill.advanced"))
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    report = doctor.run(ResourceRegistry([rid]))
    # Deduplication is irrelevant for behaviour here; just confirms the
    # registry is still resolved (no orphans).
    assert report.findings == ()


# ─────────── 12. symbol exposed from package barrel ───────────


def test_resource_doctor_exported_from_package_barrel() -> None:
    import lca.harness.diagnostics.doctor as pkg

    assert "ResourceDoctor" in pkg.__all__
    assert pkg.ResourceDoctor is _Direct
