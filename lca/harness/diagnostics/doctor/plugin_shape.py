"""Plugin shape doctor pass (ADR-0199 §5 / P2-04).

Per ADR-0199 §5.1: Doctor must NOT be a third parallel rule engine.
This pass WRAPS ``scripts/check_plugin_shape.py``: it invokes the
script as a subprocess and converts its JSON findings into
``DoctorFinding`` records with stable ``DOC-PS-*`` codes.

Per I-HPC-7: no K3 boot, no journal writes, no network I/O. The
wrapped script is read-only by design.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
    DoctorSeverity,
)

_OWNER_ADR: str = "ADR-0199"

# DOC-PS-* stable codes per scripts/check_plugin_shape.py dimension (kind).
# Source of truth for kinds: scripts/check_plugin_shape.py ALL_KINDS.
# Keep in sync with docs/specs/0199-implementation-plan.md §5 P2-04.
_CODE_BY_KIND: dict[str, str] = {
    "missing_effects": "DOC-PS-001",
    "dual_form_residue": "DOC-PS-002",
    "duplicate_id": "DOC-PS-003",
    "plugin_location": "DOC-PS-004",
    "orphan_plugin": "DOC-PS-005",
    "dead_bundle_ref": "DOC-PS-006",
    "plugin_in_init": "DOC-PS-007",
}

# Severity bands mirror check_plugin_shape.py semantics:
#   * structural / contract violations = error (must fix)
#   * convention / orphan references = warning (should fix)
# Unknown kinds default to "info" (defensive; never fail-loud on a
# kind the doctor doesn't yet understand).
_SEVERITY_BY_KIND: dict[str, DoctorSeverity] = {
    "missing_effects": "error",
    "dual_form_residue": "error",
    "duplicate_id": "error",
    "plugin_location": "error",
    "orphan_plugin": "warning",
    "dead_bundle_ref": "warning",
    "plugin_in_init": "error",
}

# Suffix used when the wrapped script is missing — distinct from the
# dimension codes (DOC-PS-9xx reserved for doctor-internal failures).
_MISSING_SCRIPT_CODE: str = "DOC-PS-901"
_UNKNOWN_KIND_CODE: str = "DOC-PS-999"

_DEFAULT_SCRIPT_REL: str = "scripts/check_plugin_shape.py"


class PluginShapeDoctor:
    """Single doctor pass: plugin shape → DoctorReport (ADR-0199 P2-04).

    The pass is a thin wrapper around ``scripts/check_plugin_shape.py``.
    It invokes the script as a subprocess and converts each violation
    into a ``DoctorFinding`` with a stable ``DOC-PS-*`` code.

    Profile-independent: this pass audits the repository's plugin tree,
    not a single profile. ``run(profile_path)`` accepts a profile_path
    argument for facade-shape parity with ``ProfileCompileDryRun`` but
    does not use it.
    """

    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        check_script: str | Path | None = None,
    ) -> None:
        self._repo_root = Path(repo_root) if repo_root else Path.cwd()
        if check_script is None:
            check_script = self._repo_root / _DEFAULT_SCRIPT_REL
        self._script = Path(check_script)

    def run(
        self,
        profile_path: str | Path | None = None,
    ) -> DoctorReport:
        """Run plugin shape audit, convert findings to DoctorReport.

        ``profile_path`` is accepted for facade-shape parity with
        ``ProfileCompileDryRun.run(profile_path)`` but is NOT used by
        this pass (plugin shape is profile-independent).

        Returns a ``DoctorReport`` whose subject is ``"plugin_shape"``
        and whose findings carry ``DOC-PS-*`` codes.
        """
        # Per I-HPC-7: profile_path is intentionally ignored. Doctor
        # audits the repo plugin tree, not a single profile.
        del profile_path

        subject = "plugin_shape"
        findings: list[DoctorFinding] = []

        if not self._script.is_file():
            findings.append(
                DoctorFinding(
                    code=_MISSING_SCRIPT_CODE,
                    severity="error",
                    owner=_OWNER_ADR,
                    message=f"check_plugin_shape.py not found at {self._script}",
                    remediation=(
                        "Verify scripts/check_plugin_shape.py exists. The doctor "
                        "wraps it; the script is the source of truth for the audit."
                    ),
                    plugin_id=None,
                    plan_ref=None,
                )
            )
            return DoctorReport.from_findings(subject, findings)

        try:
            raw = self._invoke_script()
        except RuntimeError:
            raise
        except FileNotFoundError as exc:
            findings.append(
                DoctorFinding(
                    code=_MISSING_SCRIPT_CODE,
                    severity="error",
                    owner=_OWNER_ADR,
                    message=f"check_plugin_shape.py could not be executed: {exc}",
                    remediation=(
                        "Verify Python is available and scripts/check_plugin_shape.py "
                        "is executable. The doctor wraps it; the script is the source "
                        "of truth for the audit."
                    ),
                    plugin_id=None,
                    plan_ref=None,
                )
            )
            return DoctorReport.from_findings(subject, findings)

        # Parse output shape (scripts/check_plugin_shape.py --json):
        #   {
        #     "root": "...",
        #     "total_plugins": int,
        #     "by_kind": {...},
        #     "baseline": {...},
        #     "regression": {...},
        #     "violations": [{"kind": str, "id": str, "file": str,
        #                    "line": int, "detail": str}, ...]
        #   }
        for v in raw.get("violations", []):
            kind = v.get("kind", "")
            code = _CODE_BY_KIND.get(kind, _UNKNOWN_KIND_CODE)
            severity = _SEVERITY_BY_KIND.get(kind, "info")
            plugin_id_raw = v.get("id")
            plugin_id = plugin_id_raw if isinstance(plugin_id_raw, str) else None
            message = v.get("detail") or f"plugin shape violation: {kind}"
            file_path = v.get("file")
            line_no = v.get("line")
            location = _format_location(file_path, line_no)
            remediation = _remediation_for(kind, location)
            findings.append(
                DoctorFinding(
                    code=code,
                    severity=severity,
                    owner=_OWNER_ADR,
                    message=f"{location}{message}" if location else message,
                    remediation=remediation,
                    plugin_id=plugin_id,
                    plan_ref=None,
                )
            )

        return DoctorReport.from_findings(subject, findings)

    def _invoke_script(self) -> dict[str, Any]:
        """Invoke check_plugin_shape.py as a subprocess; return parsed JSON.

        The script is invoked with ``--json --no-baseline-gate`` so:
          * output is always machine-readable JSON;
          * exit code is non-zero iff there are violations (not iff the
            baseline regressed), which keeps subprocess result codes
            transparent to the caller.
        """
        result = subprocess.run(  # noqa: S603 — script path is repo-controlled, validated
            [sys.executable, str(self._script), "--json", "--no-baseline-gate"],
            capture_output=True,
            text=True,
            cwd=self._repo_root,
            check=False,
        )
        # Exit codes from the script:
        #   0 → no violations
        #   1 → violations present (--no-baseline-gate mode)
        #   other → unexpected failure (real error)
        if result.returncode not in (0, 1):
            raise RuntimeError(
                f"check_plugin_shape.py failed unexpectedly (exit {result.returncode}): "
                f"{result.stderr[:500]}"
            )
        # The script may emit non-JSON lines (e.g., future logging); find
        # the first JSON object on stdout.
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("{"):
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed
        # Fallback: no JSON found → empty report.
        return {"violations": []}


def _format_location(file_path: Any, line_no: Any) -> str:
    """Render ``file:line`` prefix; returns "" when location is missing."""
    if not isinstance(file_path, str) or not file_path:
        return ""
    if isinstance(line_no, int) and line_no > 0:
        return f"{file_path}:{line_no}: "
    return f"{file_path}: "


def _remediation_for(kind: str, location: str) -> str:
    """Human-readable remediation hint per check_plugin_shape.py kind."""
    if kind == "missing_effects":
        return (
            "Add an effects= keyword argument to the @plugin(...) decorator. "
            "Every plugin must declare its side-effect surface."
        )
    if kind == "dual_form_residue":
        return (
            "Drop one of event_plugin_spec or plugin_spec dict in the events "
            "manifest; keep a single Manifest form per plugin."
        )
    if kind == "duplicate_id":
        return (
            "Collapse duplicate @plugin(id=...) declarations into a single file. "
            "Single-entry universe: one plugin id → one file."
        )
    if kind == "plugin_location":
        return (
            "Move the @plugin decorator into lca/plugins/ (or lca_kernel/events/"
            "manifest.py for event plugins). Test fixtures are exempt."
        )
    if kind == "orphan_plugin":
        return (
            "Reference the plugin module via $module from a bundles/*.yaml entry, "
            "or remove the orphan file."
        )
    if kind == "dead_bundle_ref":
        return (
            "Repair the bundle's $module path so it import-resolves, and ensure "
            "its @plugin(id=...) matches the bundle entry id."
        )
    if kind == "plugin_in_init":
        return (
            "Move the @plugin(...) decorator out of __init__.py into a dedicated "
            "module — one plugin per file (AGENTS.md §5)."
        )
    return (
        f"Consult scripts/check_plugin_shape.py docstring for violation semantics (kind={kind!r})."
    )


__all__ = ("_CODE_BY_KIND", "PluginShapeDoctor")
