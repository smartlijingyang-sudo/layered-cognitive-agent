"""Behavioral tests for the trust doctor pass (PR-0199-P5-04).

Covers ADR-0199 §5 + §10 Phase 5 + HPC-L7: external_kind vs privilege
declaration consistency, emitting ``DOC-TRUST-001`` findings on
conflict.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

import pytest

from lca.contracts.harness.composition.plugin_contract import (
    PluginContract,
    PluginIdentity,
)
from lca.contracts.runtime.external_plugin import ExternalPluginKind
from lca.harness.diagnostics.doctor import (
    PRIVILEGE_KIND_REQUIREMENTS,
    TrustDoctor,
)


@dataclass(frozen=True)
class _ContractShim:
    """Minimal PluginContract stand-in for unit tests.

    ``TrustDoctor.run`` only reads ``identity.id`` and ``privileges``;
    the rest is filled with the dataclass defaults so equality checks
    remain deterministic.
    """

    identity: PluginIdentity
    privileges: tuple[str, ...]


def _contract_for(plugin_id: str, privileges: tuple[str, ...]) -> PluginContract:
    return PluginContract(
        identity=PluginIdentity(id=plugin_id),
        privileges=privileges,
    )


def _run(
    plugin_contracts: list[PluginContract],
    kinds: dict[str, ExternalPluginKind],
) -> Any:
    return TrustDoctor().run(plugin_contracts, external_kind_by_plugin=kinds)


# ── state.write requires inprocess (C4 Reducer 单写) ────────────────


def test_inprocess_plugin_with_state_write_no_finding() -> None:
    report = _run(
        [_contract_for("plugin", ("state.write",))],
        {"plugin": "inprocess"},
    )
    assert not any(f.code == "DOC-TRUST-001" for f in report.findings)


def test_mcp_plugin_with_state_write_emits_doc_trust_001() -> None:
    report = _run(
        [_contract_for("plugin", ("state.write",))],
        {"plugin": "mcp"},
    )
    finding = next(f for f in report.findings if f.code == "DOC-TRUST-001")
    assert "state.write" in finding.message
    assert "mcp" in finding.message
    assert finding.plugin_id == "plugin"


def test_sandbox_plugin_with_state_write_emits_doc_trust_001() -> None:
    report = _run(
        [_contract_for("plugin", ("state.write",))],
        {"plugin": "sandbox"},
    )
    assert any(f.code == "DOC-TRUST-001" for f in report.findings)


# ── network.egress requires mcp or sandbox ───────────────────────────


def test_inprocess_plugin_with_network_egress_emits_doc_trust_001() -> None:
    report = _run(
        [_contract_for("plugin", ("network.egress",))],
        {"plugin": "inprocess"},
    )
    finding = next(f for f in report.findings if f.code == "DOC-TRUST-001")
    assert "network.egress" in finding.message


def test_mcp_plugin_with_network_egress_no_finding() -> None:
    report = _run(
        [_contract_for("plugin", ("network.egress",))],
        {"plugin": "mcp"},
    )
    assert not any(f.code == "DOC-TRUST-001" for f in report.findings)


def test_sandbox_plugin_with_network_egress_no_finding() -> None:
    report = _run(
        [_contract_for("plugin", ("network.egress",))],
        {"plugin": "sandbox"},
    )
    assert not any(f.code == "DOC-TRUST-001" for f in report.findings)


# ── journal.append requires inprocess or worker ──────────────────────


def test_inprocess_plugin_with_journal_append_no_finding() -> None:
    report = _run(
        [_contract_for("plugin", ("journal.append",))],
        {"plugin": "inprocess"},
    )
    assert not any(f.code == "DOC-TRUST-001" for f in report.findings)


def test_worker_plugin_with_journal_append_no_finding() -> None:
    report = _run(
        [_contract_for("plugin", ("journal.append",))],
        {"plugin": "worker"},
    )
    assert not any(f.code == "DOC-TRUST-001" for f in report.findings)


def test_mcp_plugin_with_journal_append_emits_doc_trust_001() -> None:
    report = _run(
        [_contract_for("plugin", ("journal.append",))],
        {"plugin": "mcp"},
    )
    assert any(f.code == "DOC-TRUST-001" for f in report.findings)


# ── process.spawn requires sandbox ───────────────────────────────────


def test_sandbox_plugin_with_process_spawn_no_finding() -> None:
    report = _run(
        [_contract_for("plugin", ("process.spawn",))],
        {"plugin": "sandbox"},
    )
    assert not any(f.code == "DOC-TRUST-001" for f in report.findings)


def test_mcp_plugin_with_process_spawn_emits_doc_trust_001() -> None:
    report = _run(
        [_contract_for("plugin", ("process.spawn",))],
        {"plugin": "mcp"},
    )
    finding = next(f for f in report.findings if f.code == "DOC-TRUST-001")
    assert "process.spawn" in finding.message


# ── no requirement (memory., tools., k3., policy., fs.) ──────────────


def test_unknown_privilege_prefix_no_finding() -> None:
    # ``tools.invoke`` has no requirement → every kind is fine.
    for kind in ("inprocess", "mcp", "sandbox", "worker"):
        report = _run(
            [_contract_for("plugin", ("tools.invoke",))],
            {"plugin": kind},
        )
        assert not any(f.code == "DOC-TRUST-001" for f in report.findings), (
            f"tools.invoke with kind={kind} should not emit DOC-TRUST-001"
        )


# ── default external_kind fallback ───────────────────────────────────


def test_default_kind_is_inprocess_when_not_in_map() -> None:
    # Plugin absent from the map defaults to inprocess; a state.write
    # privilege must therefore not emit DOC-TRUST-001.
    report = _run(
        [_contract_for("missing", ("state.write",))],
        kinds={},
    )
    assert not any(f.code == "DOC-TRUST-001" for f in report.findings)


def test_default_kind_with_mismatched_privilege_still_emits() -> None:
    # network.egress against an absent-from-map plugin (defaults to
    # inprocess) must still emit DOC-TRUST-001.
    report = _run(
        [_contract_for("missing", ("network.egress",))],
        kinds={},
    )
    assert any(f.code == "DOC-TRUST-001" for f in report.findings)


# ── multi-plugin fan-out ─────────────────────────────────────────────


def test_multiple_plugins_each_audited_separately() -> None:
    report = _run(
        [
            _contract_for("clean", ("state.write",)),
            _contract_for("dirty", ("state.write",)),
        ],
        {"clean": "inprocess", "dirty": "mcp"},
    )
    trust_findings = [f for f in report.findings if f.code == "DOC-TRUST-001"]
    assert {f.plugin_id for f in trust_findings} == {"dirty"}


def test_per_plugin_findings_carries_plugin_id() -> None:
    report = _run(
        [
            _contract_for("alpha", ("network.egress",)),
            _contract_for("beta", ("process.spawn",)),
        ],
        {"alpha": "inprocess", "beta": "mcp"},
    )
    by_plugin: dict[str | None, list[Any]] = {}
    for finding in report.findings:
        by_plugin.setdefault(finding.plugin_id, []).append(finding)
    assert "alpha" in by_plugin
    assert "beta" in by_plugin


# ── invariants ───────────────────────────────────────────────────────


def test_no_io_side_effects() -> None:
    module = import_module("lca.harness.diagnostics.doctor.trust")
    assert module.__all__ == ("PRIVILEGE_KIND_REQUIREMENTS", "TrustDoctor")
    forbidden = ("subprocess", "urllib", "requests", "httpx", "socket")
    assert all(name not in module.__dict__ for name in forbidden)


def test_doc_trust_001_severity_is_error() -> None:
    report = _run(
        [_contract_for("plugin", ("state.write",))],
        {"plugin": "mcp"},
    )
    finding = next(f for f in report.findings if f.code == "DOC-TRUST-001")
    assert finding.severity == "error"


def test_doc_trust_001_has_owner_and_remediation() -> None:
    report = _run(
        [_contract_for("plugin", ("network.egress",))],
        {"plugin": "inprocess"},
    )
    finding = next(f for f in report.findings if f.code == "DOC-TRUST-001")
    assert finding.owner == "ADR-0199"
    assert "trust rubric" in finding.remediation


# ── barrel + requirement table exposure ──────────────────────────────


def test_barrel_exports_trust_doctor_and_table() -> None:
    from lca.harness.diagnostics.doctor import __all__

    assert "TrustDoctor" in __all__
    assert "PRIVILEGE_KIND_REQUIREMENTS" in __all__


def test_requirement_table_matches_rubric() -> None:
    assert PRIVILEGE_KIND_REQUIREMENTS["state."] == frozenset({"inprocess"})
    assert PRIVILEGE_KIND_REQUIREMENTS["journal."] == frozenset({"inprocess", "worker"})
    assert PRIVILEGE_KIND_REQUIREMENTS["network."] == frozenset({"mcp", "sandbox"})
    assert PRIVILEGE_KIND_REQUIREMENTS["process."] == frozenset({"sandbox"})


@pytest.mark.parametrize(
    ("privilege", "kind", "expect_finding"),
    [
        ("state.write", "inprocess", False),
        ("state.write", "mcp", True),
        ("state.write", "sandbox", True),
        ("state.write", "worker", True),
        ("journal.append", "inprocess", False),
        ("journal.append", "worker", False),
        ("journal.append", "mcp", True),
        ("journal.append", "sandbox", True),
        ("network.egress", "mcp", False),
        ("network.egress", "sandbox", False),
        ("network.egress", "inprocess", True),
        ("network.egress", "worker", True),
        ("process.spawn", "sandbox", False),
        ("process.spawn", "inprocess", True),
        ("process.spawn", "mcp", True),
        ("process.spawn", "worker", True),
        ("memory.write", "inprocess", False),
        ("memory.write", "sandbox", False),
        ("tools.invoke", "mcp", False),
        ("policy.gate", "worker", False),
        ("k3.boot", "sandbox", False),
        ("fs.write", "inprocess", False),  # fs. not in requirement table
    ],
)
def test_privilege_kind_matrix(
    privilege: str,
    kind: ExternalPluginKind,
    expect_finding: bool,
) -> None:
    report = _run(
        [_contract_for("plugin", (privilege,))],
        {"plugin": kind},
    )
    has = any(f.code == "DOC-TRUST-001" for f in report.findings)
    assert has is expect_finding, (
        f"privilege={privilege!r} kind={kind!r} expected "
        f"{'finding' if expect_finding else 'no finding'}, got has={has}"
    )


def test_empty_contracts_no_findings() -> None:
    assert _run([], kinds={}).findings == ()


def test_empty_privileges_no_findings() -> None:
    report = _run(
        [_contract_for("plugin", ())],
        {"plugin": "mcp"},
    )
    assert not any(f.code == "DOC-TRUST-001" for f in report.findings)


def test_multiple_conflicting_privileges_emit_multiple_findings() -> None:
    # inprocess plugin with both state.write and network.egress:
    # state.write is fine; network.egress is the only mismatch.
    report = _run(
        [_contract_for("plugin", ("state.write", "network.egress"))],
        {"plugin": "inprocess"},
    )
    findings = [f for f in report.findings if f.code == "DOC-TRUST-001"]
    assert len(findings) == 1
    assert "network.egress" in findings[0].message
