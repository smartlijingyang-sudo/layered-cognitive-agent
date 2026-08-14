"""Preinstall SSOT — catalog ↔ requirements-python.txt parity."""

from __future__ import annotations

import re
from pathlib import Path

from lca.contracts.models.core.preinstall import (
    KEY_PYTHON_IMPORTS,
    SANDBOX_PREINSTALLED_PYTHON_PACKAGES,
    python_import_name,
)
from lca.layer0_infra.tools.lca_computer.manifest import (
    CLOUD_SANDBOX_MANIFEST,
    MACHINE_MANIFEST,
)
from lca.layer0_infra.tools.lca_computer.types import SANDBOX_ONLY_APIS


def _requirements_names(path: Path) -> set[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.split("#", 1)[0].strip()
        if not text or text.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", text)
        if match:
            names.add(match.group(1).lower())
    return names


def test_machine_manifest_excludes_sandbox_only_apis() -> None:
    machine_api_names = {api.name for api in MACHINE_MANIFEST.api}
    assert SANDBOX_ONLY_APIS.isdisjoint(machine_api_names)
    assert len(machine_api_names) == 11


def test_cloud_manifest_includes_all_apis() -> None:
    assert len(CLOUD_SANDBOX_MANIFEST.api) == 13


def test_key_imports_subset_of_catalog() -> None:
    catalog = {python_import_name(p) for p in SANDBOX_PREINSTALLED_PYTHON_PACKAGES}
    for name in KEY_PYTHON_IMPORTS:
        assert name in catalog


def test_requirements_txt_covers_preinstall_catalog() -> None:
    req_path = Path("deploy/onlyboxes/requirements-python.txt")
    listed = _requirements_names(req_path)
    missing = [
        pkg
        for pkg in SANDBOX_PREINSTALLED_PYTHON_PACKAGES
        if pkg.lower() not in listed
    ]
    assert not missing, f"requirements-python.txt missing: {missing}"
