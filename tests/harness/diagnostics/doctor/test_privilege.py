"""Behavioral tests for the privilege doctor pass (PR-0199-P3-05)."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

import pytest

from lca.contracts.harness.composition.plugin_contract import (
    PRIVILEGE_PREFIXES,
    CapabilityContract,
    PluginContract,
    PluginIdentity,
)
from lca.harness.diagnostics.doctor import PrivilegeDoctor


@dataclass(frozen=True)
class _ContractShim:
    identity: PluginIdentity
    capabilities: CapabilityContract
    privileges: tuple[str, ...]


def _run(
    plugin_contracts: list[tuple[str, tuple[str, ...], tuple[str, ...]]],
) -> Any:
    return PrivilegeDoctor().run(
        [
            _ContractShim(
                identity=PluginIdentity(id=plugin_id),
                capabilities=CapabilityContract(effect_classes=effects),
                privileges=privileges,
            )
            for plugin_id, privileges, effects in plugin_contracts
        ]
    )


def test_empty_contracts_no_findings() -> None:
    assert _run([]).findings == ()


def test_clean_privileges_and_effects_emits_no_errors() -> None:
    report = _run([("plugin", ("tools.invoke",), ("tools.call",))])
    assert not report.has_errors()


@pytest.mark.parametrize("prefix", sorted(PRIVILEGE_PREFIXES))
def test_known_privilege_prefix_accepted(prefix: str) -> None:
    report = _run([("plugin", (f"{prefix}action",), (f"{prefix}effect",))])
    assert not report.has_errors()


def test_unknown_privilege_prefix_emits_doc_priv_002() -> None:
    report = _run([("plugin", ("custom.action",), ())])
    finding = next(item for item in report.findings if item.code == "DOC-PRIV-002")
    assert "custom.action" in finding.message


def test_doc_priv_002_severity_is_error() -> None:
    report = _run([("plugin", ("custom.action",), ())])
    finding = next(item for item in report.findings if item.code == "DOC-PRIV-002")
    assert finding.severity == "error"


def test_orphan_privileges_emits_doc_priv_003() -> None:
    report = _run([("plugin", ("state.write",), ())])
    assert any(item.code == "DOC-PRIV-003" for item in report.findings)


def test_doc_priv_003_severity_is_warning() -> None:
    report = _run([("plugin", ("state.write",), ())])
    finding = next(item for item in report.findings if item.code == "DOC-PRIV-003")
    assert finding.severity == "warning"


def test_effect_without_matching_privilege_emits_doc_priv_001() -> None:
    report = _run([("plugin", (), ("network.egress",))])
    finding = next(item for item in report.findings if item.code == "DOC-PRIV-001")
    assert "network.egress" in finding.message


def test_doc_priv_001_severity_is_error() -> None:
    report = _run([("plugin", (), ("network.egress",))])
    finding = next(item for item in report.findings if item.code == "DOC-PRIV-001")
    assert finding.severity == "error"


def test_matching_privilege_and_effect_no_findings() -> None:
    report = _run([("plugin", ("memory.write",), ("memory.persist",))])
    assert not report.has_errors()


def test_multiple_plugins_each_audited_separately() -> None:
    report = _run(
        [
            ("one", ("tools.invoke",), ("tools.call",)),
            ("two", ("network.egress",), ("network.request",)),
        ]
    )
    assert not report.has_errors()


def test_clean_audit_emits_doc_priv_004_info() -> None:
    report = _run([("plugin", ("state.write",), ("state.commit",))])
    finding = next(item for item in report.findings if item.code == "DOC-PRIV-004")
    assert finding.severity == "info"
    assert "1 unique privileges" in finding.message


def test_audit_with_findings_does_not_emit_doc_priv_004() -> None:
    report = _run([("plugin", ("custom.action",), ())])
    assert not any(item.code == "DOC-PRIV-004" for item in report.findings)


def test_finding_carries_plugin_id() -> None:
    report = _run([("plugin.example", (), ("network.egress",))])
    assert {item.plugin_id for item in report.findings} == {"plugin.example"}


def test_no_io_side_effects() -> None:
    module = import_module("lca.harness.diagnostics.doctor.privilege")
    assert module.__all__ == ("PrivilegeDoctor",)
    forbidden = ("subprocess", "urllib", "requests", "httpx", "socket")
    assert all(name not in module.__dict__ for name in forbidden)


def test_real_plugin_contract_is_accepted() -> None:
    contract = PluginContract(
        identity=PluginIdentity(id="real.plugin"),
        capabilities=CapabilityContract(effect_classes=("journal.append",)),
        privileges=("journal.append",),
    )
    report = PrivilegeDoctor().run([contract])
    assert len(report.findings) == 1
    assert report.findings[0].code == "DOC-PRIV-004"


def test_effect_prefix_matches_privilege_scope() -> None:
    report = _run([("plugin", ("tools.read",), ("tools.invoke.named",))])
    assert not report.has_errors()


def test_barrel_exports_privilege_doctor() -> None:
    from lca.harness.diagnostics.doctor import __all__

    assert "PrivilegeDoctor" in __all__
