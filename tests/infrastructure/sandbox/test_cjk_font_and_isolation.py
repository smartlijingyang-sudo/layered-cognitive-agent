"""Tests for systemic Fontconfig CJK alias mapping and run workspace isolation (ADR-0244 PR-4)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from lca.contracts.models.core.execution.sandbox import SANDBOX_MOUNT_ROOT
from lca.contracts.models.core.state.guest_layout import GuestLayout


def test_guest_layout_for_run_isolation() -> None:
    """GuestLayout.for_run produces isolated workspace paths scoped per run."""
    run_1_layout = GuestLayout.for_run("run_abc_123")
    run_2_layout = GuestLayout.for_run("run_xyz_789")

    assert run_1_layout.root == f"{SANDBOX_MOUNT_ROOT}/runs/run_abc_123"
    assert run_2_layout.root == f"{SANDBOX_MOUNT_ROOT}/runs/run_xyz_789"
    assert run_1_layout.root != run_2_layout.root

    assert run_1_layout.outputs_dir == f"{SANDBOX_MOUNT_ROOT}/runs/run_abc_123/outputs"
    assert run_2_layout.outputs_dir == f"{SANDBOX_MOUNT_ROOT}/runs/run_xyz_789/outputs"
    assert run_1_layout.outputs_dir != run_2_layout.outputs_dir

    assert run_1_layout.output_file("report.pdf") == (
        f"{SANDBOX_MOUNT_ROOT}/runs/run_abc_123/outputs/report.pdf"
    )
    assert run_2_layout.output_file("report.pdf") == (
        f"{SANDBOX_MOUNT_ROOT}/runs/run_xyz_789/outputs/report.pdf"
    )


def test_guest_layout_for_run_path_traversal_protection() -> None:
    """GuestLayout.for_run sanitizes dirty or traversal-prone run IDs."""
    dirty_layout = GuestLayout.for_run("/../../escape/run")
    assert dirty_layout.root == f"{SANDBOX_MOUNT_ROOT}/runs/escape/run"

    empty_layout = GuestLayout.for_run("")
    assert empty_layout.root == f"{SANDBOX_MOUNT_ROOT}/runs/default"


def test_fontconfig_local_conf_structure_and_cjk_fallbacks() -> None:
    """Validate system-level Fontconfig XML configuration in deploy/onlyboxes/local.conf."""
    repo_root = Path(__file__).resolve().parents[3]
    local_conf_path = repo_root / "deploy" / "onlyboxes" / "local.conf"

    assert local_conf_path.exists(), "deploy/onlyboxes/local.conf must exist"

    # Must be valid XML
    tree = ET.parse(local_conf_path)  # noqa: S314
    root = tree.getroot()
    assert root.tag == "fontconfig"

    # Collect all matched families and their target edits
    matched_families: dict[str, list[str]] = {}
    for match in root.findall("match"):
        target = match.attrib.get("target")
        if target != "pattern":
            continue
        test_elem = match.find("test")
        edit_elem = match.find("edit")
        if test_elem is not None and edit_elem is not None:
            name_attr = test_elem.attrib.get("name")
            if name_attr == "family":
                test_str = test_elem.find("string")
                if test_str is not None and test_str.text:
                    src_family = test_str.text.strip()
                    targets = [
                        s.text.strip() for s in edit_elem.findall("string") if s.text
                    ]
                    matched_families[src_family] = targets

    # Assert essential fallbacks are declared
    required_families = [
        "sans-serif",
        "serif",
        "monospace",
        "SimHei",
        "Microsoft YaHei",
        "Arial",
        "Helvetica",
    ]
    for fam in required_families:
        assert fam in matched_families, f"Missing Fontconfig fallback for family: {fam}"
        targets = matched_families[fam]
        assert any(
            "WenQuanYi" in t or "Noto" in t for t in targets
        ), f"Family {fam} does not map to any CJK font: {targets}"


def test_dockerfiles_include_local_conf() -> None:
    """Verify Dockerfiles install local.conf to /etc/fonts/local.conf."""
    repo_root = Path(__file__).resolve().parents[3]
    dockerfiles = [
        repo_root / "deploy" / "onlyboxes" / "Dockerfile.python",
        repo_root / "deploy" / "onlyboxes" / "Dockerfile.terminal",
    ]
    for df in dockerfiles:
        assert df.exists(), f"Dockerfile not found: {df}"
        content = df.read_text(encoding="utf-8")
        assert "COPY local.conf /etc/fonts/local.conf" in content, (
            f"{df.name} must copy local.conf to /etc/fonts/local.conf"
        )
