"""Behavioral tests for the CapabilityCardinalityDoctor pass (PR-0199-P2-05).

Per ADR-0199 §2.3 each capability key may have AT MOST ONE active
provider. The pass is read-only (I-HPC-7) and deterministic (C8);
these tests assert both properties without booting K3, without
journal writes, and without filesystem side effects.
"""

from __future__ import annotations

import re
import subprocess  # noqa: F401 — used in test_no_io_side_effects
from dataclasses import dataclass

import pytest

from lca.contracts.diagnostics.doctor import DoctorFinding, DoctorReport
from lca.harness.diagnostics.doctor import CapabilityCardinalityDoctor

# Stable machine-code regex copied verbatim from
# lca.contracts.diagnostics.doctor (DOC-<DOMAIN>-<NNN>).
_CODE_RE = re.compile(r"^DOC-[A-Z]{2,6}-\d{3,}$")


# ─────────── test fixtures ───────────


@dataclass(frozen=True)
class _StubPlugin:
    """Minimal stand-in for PluginContract.

    `CapabilityCardinalityDoctor` only reads
    `contract.identity.id` and `contract.capabilities.provides`, so a
    faithful shim is all the pass needs. Using a dataclass keeps the
    stub frozen (slot-equivalent) for the immutability assertion.
    """

    plugin_id: str
    provides: tuple[str, ...] = ()


def _wrap(stubs: list[_StubPlugin]) -> list:
    """Translate `_StubPlugin` records into objects exposing the real
    `PluginContract` attribute shape (`identity.id`, `capabilities.provides`)."""

    @dataclass(frozen=True)
    class _Identity:
        id: str

    @dataclass(frozen=True)
    class _Capabilities:
        provides: tuple[str, ...]

    @dataclass(frozen=True)
    class _Shim:
        identity: _Identity
        capabilities: _Capabilities

    return [
        _Shim(identity=_Identity(id=s.plugin_id), capabilities=_Capabilities(provides=s.provides))
        for s in stubs
    ]


# ─────────── 1. empty / trivial inputs ───────────


def test_empty_contracts_yields_empty_report() -> None:
    doctor = CapabilityCardinalityDoctor()
    report = doctor.run([])
    assert isinstance(report, DoctorReport)
    assert report.findings == ()
    assert report.summary.total == 0
    assert report.summary.errors == 0


def test_single_contract_no_findings() -> None:
    doctor = CapabilityCardinalityDoctor()
    report = doctor.run(_wrap([_StubPlugin("memory.lancedb", provides=("memory.semantic",))]))
    assert report.findings == ()
    assert report.summary.total == 0


def test_distinct_capabilities_no_findings() -> None:
    doctor = CapabilityCardinalityDoctor()
    stubs = [
        _StubPlugin("a", provides=("memory.semantic",)),
        _StubPlugin("b", provides=("memory.episodic",)),
        _StubPlugin("c", provides=("llm.primary",)),
    ]
    report = doctor.run(_wrap(stubs))
    assert report.findings == ()


# ─────────── 2. duplicate emission ───────────


def test_duplicate_capability_emits_doc_cap_001() -> None:
    doctor = CapabilityCardinalityDoctor()
    stubs = [
        _StubPlugin("memory.alpha", provides=("memory.semantic",)),
        _StubPlugin("memory.beta", provides=("memory.semantic",)),
    ]
    report = doctor.run(_wrap(stubs))
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.code == "DOC-CAP-001"
    assert "memory.semantic" in finding.message


def test_triplicate_capability_still_one_finding() -> None:
    doctor = CapabilityCardinalityDoctor()
    stubs = [
        _StubPlugin("memory.alpha", provides=("memory.semantic",)),
        _StubPlugin("memory.beta", provides=("memory.semantic",)),
        _StubPlugin("memory.gamma", provides=("memory.semantic",)),
    ]
    report = doctor.run(_wrap(stubs))
    assert len(report.findings) == 1
    assert report.findings[0].code == "DOC-CAP-001"
    msg = report.findings[0].message
    assert "memory.alpha" in msg
    assert "memory.beta" in msg
    assert "memory.gamma" in msg
    assert "3 active providers" in msg


def test_finding_message_lists_all_providers() -> None:
    doctor = CapabilityCardinalityDoctor()
    stubs = [
        _StubPlugin("plugin.z", provides=("cap.x",)),
        _StubPlugin("plugin.a", provides=("cap.x",)),
        _StubPlugin("plugin.m", provides=("cap.x",)),
    ]
    report = doctor.run(_wrap(stubs))
    assert len(report.findings) == 1
    message = report.findings[0].message
    # All three ids must appear (sorted: a, m, z).
    assert "plugin.a" in message
    assert "plugin.m" in message
    assert "plugin.z" in message


# ─────────── 3. severity / code / remediation ───────────


def test_finding_is_error_severity() -> None:
    doctor = CapabilityCardinalityDoctor()
    stubs = [
        _StubPlugin("a", provides=("c",)),
        _StubPlugin("b", provides=("c",)),
    ]
    report = doctor.run(_wrap(stubs))
    assert report.summary.errors == 1
    assert report.summary.warnings == 0
    assert report.summary.info == 0
    assert report.has_errors() is True
    assert report.findings[0].severity == "error"


def test_finding_code_matches_doc_cap_regex() -> None:
    doctor = CapabilityCardinalityDoctor()
    stubs = [
        _StubPlugin("a", provides=("c",)),
        _StubPlugin("b", provides=("c",)),
    ]
    report = doctor.run(_wrap(stubs))
    code = report.findings[0].code
    assert _CODE_RE.match(code), f"code {code!r} does not match DOC-<DOMAIN>-<NNN>"
    assert code == "DOC-CAP-001"


def test_finding_remediation_is_non_empty() -> None:
    doctor = CapabilityCardinalityDoctor()
    stubs = [
        _StubPlugin("a", provides=("c",)),
        _StubPlugin("b", provides=("c",)),
    ]
    report = doctor.run(_wrap(stubs))
    assert report.findings[0].remediation.strip() != ""
    # The remediation must point at the ADR so CI suppression is auditable.
    assert "ADR-0199" in report.findings[0].remediation


# ─────────── 4. uniqueness at scale ───────────


def test_no_findings_when_each_capability_is_unique() -> None:
    doctor = CapabilityCardinalityDoctor()
    stubs = [
        _StubPlugin("p1", provides=("cap.a",)),
        _StubPlugin("p2", provides=("cap.b",)),
        _StubPlugin("p3", provides=("cap.c",)),
        _StubPlugin("p4", provides=("cap.d",)),
        _StubPlugin("p5", provides=("cap.e",)),
    ]
    report = doctor.run(_wrap(stubs))
    assert report.findings == ()
    assert report.summary.total == 0


# ─────────── 5. subject handling ───────────


def test_profile_path_used_as_subject_when_provided() -> None:
    doctor = CapabilityCardinalityDoctor(profile_path="/etc/lca/profiles/main.yaml")
    report = doctor.run([])
    assert report.subject == "/etc/lca/profiles/main.yaml"


def test_default_subject_when_no_profile_path() -> None:
    doctor = CapabilityCardinalityDoctor()
    report = doctor.run([])
    assert report.subject == "capability_cardinality"


# ─────────── 6. determinism (C8) ───────────


def test_findings_are_deterministic_across_calls() -> None:
    doctor = CapabilityCardinalityDoctor()
    # Build input where insertion-order differs from sorted output: this
    # would surface a missing sort() in the pass.
    stubs = [
        _StubPlugin("zeta", provides=("cap.k", "cap.j", "cap.l")),
        _StubPlugin("alpha", provides=("cap.j", "cap.i", "cap.m")),
        _StubPlugin("mid", provides=("cap.k", "cap.i", "cap.n")),
    ]
    r1 = doctor.run(_wrap(stubs))
    r2 = doctor.run(_wrap(stubs))
    # Deterministic at the bytestring level.
    assert [f.message for f in r1.findings] == [f.message for f in r2.findings]
    # And the message bodies are themselves sorted (cap.i, cap.j, cap.k).
    codes_in_order = [f.message for f in r1.findings]
    assert codes_in_order == sorted(codes_in_order)


# ─────────── 7. side-effect freedom (I-HPC-7) ───────────


def test_no_io_side_effects() -> None:
    """Module imports must not trigger subprocess, network, or writes.

    The intent here is static: the module does not import subprocess,
    os.system, urllib, requests, httpx, etc. We confirm by importing
    the module and asserting the public surface is what we expect.
    """
    import lca.harness.diagnostics.doctor.capability_cardinality as mod

    # Public API: only the doctor class.
    assert mod.__all__ == ("CapabilityCardinalityDoctor",)
    # No subprocess / network / filesystem writers in the module's globals.
    forbidden = ("subprocess", "os.system", "urllib", "requests", "httpx", "socket")
    for name in forbidden:
        assert name not in mod.__dict__, f"forbidden name {name!r} in module globals"


def test_does_not_modify_input_contracts() -> None:
    doctor = CapabilityCardinalityDoctor()
    stubs = [
        _StubPlugin("a", provides=("c",)),
        _StubPlugin("b", provides=("c",)),
    ]
    wrapped = _wrap(stubs)
    # Snapshot each shim's state before run.
    before = [(s.identity.id, tuple(s.capabilities.provides)) for s in wrapped]
    doctor.run(wrapped)
    after = [(s.identity.id, tuple(s.capabilities.provides)) for s in wrapped]
    assert before == after


# ─────────── 8. dataclass contract guarantees (smoke) ───────────


def test_finding_is_frozen_dataclass() -> None:
    """DoctorFinding is frozen; downstream tests rely on this for safe
    reuse across passes."""
    doctor = CapabilityCardinalityDoctor()
    stubs = [
        _StubPlugin("a", provides=("c",)),
        _StubPlugin("b", provides=("c",)),
    ]
    report = doctor.run(_wrap(stubs))
    finding = report.findings[0]
    assert isinstance(finding, DoctorFinding)
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError subclass
        finding.code = "DOC-CAP-999"  # type: ignore[misc]
