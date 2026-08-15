"""Execution environment preinstall catalog — SSOT for sandbox + host parity.

Python packages: ``deploy/onlyboxes/requirements-python.txt`` (physical install).
CLI tools: Dockerfiles + ``lca-host.yaml`` system_packages.
This module is the **semantic catalog** consumed by prompts, tool descriptions,
host ``check_imports``, and conformance tests.
"""

from __future__ import annotations

from lca.contracts.models.core.sandbox import (
    SANDBOX_PREINSTALLED_CLI_TOOLS,
    SANDBOX_PREINSTALLED_PYTHON_PACKAGES,
)

# Subset verified on every host provision (`./scripts/lca-ops status`).
KEY_PYTHON_IMPORTS: tuple[str, ...] = (
    "pandas",
    "numpy",
    "matplotlib",
    "openpyxl",
    "reportlab",
    "requests",
)

# Pip package name → ``import`` name when they differ.
_IMPORT_ALIASES: dict[str, str] = {
    "opencv-python-headless": "cv2",
    "python-docx": "docx",
    "fpdf2": "fpdf",
    "python-dotenv": "dotenv",
    "scikit-learn": "sklearn",
    "pillow": "PIL",
}


def python_import_name(package: str) -> str:
    """Map a requirements.txt distribution name to ``import`` name."""
    return _IMPORT_ALIASES.get(package, package.replace("-", "_").split("[")[0])


__all__ = [
    "KEY_PYTHON_IMPORTS",
    "SANDBOX_PREINSTALLED_CLI_TOOLS",
    "SANDBOX_PREINSTALLED_PYTHON_PACKAGES",
    "python_import_name",
]
