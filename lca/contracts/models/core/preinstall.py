"""Execution environment preinstall catalog — SSOT for sandbox + host parity.

Python packages: ``deploy/onlyboxes/requirements-python.txt`` (physical install).
CLI tools: Dockerfiles + ``lca-host.yaml`` system_packages.
This module is the **semantic catalog** consumed by prompts, tool descriptions,
host ``check_imports``, and conformance tests.
"""

from __future__ import annotations

from lca.contracts.models.core.plane import PlaneKind
from lca.contracts.models.core.sandbox import (
    SANDBOX_PREINSTALLED_CLI_TOOLS,
    SANDBOX_PREINSTALLED_PYTHON_PACKAGES,
)

# Subset verified on every host provision (`lca-host.py status`).
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


def render_preinstalled_block(*, plane: PlaneKind) -> str:
    """Render ``<preinstalled_software>`` body for agent system roles."""
    py = ", ".join(SANDBOX_PREINSTALLED_PYTHON_PACKAGES)
    cli = ", ".join(SANDBOX_PREINSTALLED_CLI_TOOLS)
    header = {
        PlaneKind.SANDBOX: "Cloud sandbox pre-installed software",
        PlaneKind.MACHINE: "Host machine pre-installed software (shared venv + system packages)",
    }.get(plane, "Pre-installed software")
    lines = [
        f"**{header}**",
        f"- Python packages (pip/venv): {py}",
        f"- CLI tools: {cli}",
    ]
    if plane is PlaneKind.MACHINE:
        lines.append(
            "- Use `python3` or `python` (venv); do **not** pip-install at runtime — packages are pre-provisioned."
        )
        lines.append(
            "- `executeCode` / `exportFile` are **not** available on the machine face; use cloud sandbox or `runCommand`."
        )
    else:
        lines.append("- Use `executeCode` for Python/JS/TS; deliverables under outputs/.")
        lines.append(
            "- Chinese PDF/charts: matplotlib font 'WenQuanYi Zen Hei'; reportlab CID font STSong-Light."
        )
    return "\n".join(lines)


__all__ = [
    "KEY_PYTHON_IMPORTS",
    "SANDBOX_PREINSTALLED_CLI_TOOLS",
    "SANDBOX_PREINSTALLED_PYTHON_PACKAGES",
    "python_import_name",
    "render_preinstalled_block",
]
