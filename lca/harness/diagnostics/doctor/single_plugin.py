"""Single-plugin doctor pass (ADR-0199 §5 / P2-09).

Per ADR-0199 §5.1 the doctor must walk the real plugin tree. For
single-plugin author feedback this pass audits ONE module without
booting the full kernel.

Per I-HPC-7: no K3 boot, no journal writes, no network. The pass is
pure AST analysis — no actual import, no setup() invocation.

DOC-PS-* codes mirror scripts/check_plugin_shape.py dimensions, but
scoped to one file:
  DOC-PS-001 — missing @plugin effects declaration
  DOC-PS-002 — dual manifest (event_plugin_spec + plugin_spec)
  DOC-PS-007 — @plugin in __init__.py
  DOC-PS-101 — module has no @plugin decorator
  DOC-PS-102 — module has unrecognized effects
  DOC-PS-901 — plugin file not found (doctor-internal)
  DOC-PS-902 — syntax error in plugin file (doctor-internal)
"""

from __future__ import annotations

import ast
from pathlib import Path

from lca.contracts.diagnostics.doctor import (
    DoctorFinding,
    DoctorReport,
)

_OWNER_ADR: str = "ADR-0199"

# Effect taxonomy (subset that the AST can detect statically).
_KNOWN_EFFECTS_PREFIXES: tuple[str, ...] = (
    "journal.",
    "state.",
    "memory.",
    "tools.",
    "policy.",
)


class SinglePluginDoctor:
    """Single-plugin doctor pass (ADR-0199 P2-09)."""

    def __init__(self, *, plugin_path: str | Path | None = None) -> None:
        self._plugin_path = Path(plugin_path) if plugin_path else None

    def run(self, plugin_path: str | Path) -> DoctorReport:
        """Audit a single plugin module file via AST.

        Per I-HPC-7: no import, no setup, no K3 boot.
        """
        path = Path(plugin_path)
        subject = str(path)
        findings: list[DoctorFinding] = []

        if not path.exists():
            findings.append(
                DoctorFinding(
                    code="DOC-PS-901",
                    severity="error",
                    owner=_OWNER_ADR,
                    message=f"plugin file not found: {path}",
                    remediation=(
                        "Verify the plugin path. Single-plugin doctor audits one "
                        ".py file at a time; for tree-wide audits use lca-ops doctor profile."
                    ),
                )
            )
            return DoctorReport.from_findings(subject, findings)

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            findings.append(
                DoctorFinding(
                    code="DOC-PS-902",
                    severity="error",
                    owner=_OWNER_ADR,
                    message=f"syntax error in {path.name}: line {exc.lineno}: {exc.msg}",
                    remediation="Fix the syntax error first.",
                )
            )
            return DoctorReport.from_findings(subject, findings)

        plugin_decorators = self._find_plugin_decorators(tree)
        if not plugin_decorators:
            findings.append(
                DoctorFinding(
                    code="DOC-PS-101",
                    severity="info",
                    owner=_OWNER_ADR,
                    message=f"{path.name} has no @plugin decorator",
                    remediation=(
                        "Add a @plugin decorator if this is meant to be a plugin. "
                        "Per AGENTS.md §5: '每个 plugin 一个 .py 文件'."
                    ),
                )
            )

        # Check 1: missing effects= per @plugin(...) decorator.
        for dec in plugin_decorators:
            kwargs = self._kwarg_names(dec)
            if "effects" not in kwargs:
                findings.append(
                    DoctorFinding(
                        code="DOC-PS-001",
                        severity="error",
                        owner=_OWNER_ADR,
                        message=(f"@plugin at line {dec.lineno} missing effects= keyword"),
                        remediation=(
                            "Per AGENTS.md §5 and ADR-0199 §3.3 effects must be "
                            "declared. Use EffectPolicyPlan projection or literal "
                            "effect names."
                        ),
                        plugin_id=self._extract_plugin_id(dec),
                    )
                )
            else:
                effects_value = self._extract_kwarg_value(dec, "effects")
                unknown_effects = self._check_effects(effects_value)
                for unk in unknown_effects:
                    findings.append(
                        DoctorFinding(
                            code="DOC-PS-102",
                            severity="warning",
                            owner=_OWNER_ADR,
                            message=(
                                f"effect {unk!r} is not a known prefix "
                                f"{list(_KNOWN_EFFECTS_PREFIXES)}"
                            ),
                            remediation=(
                                f"Use a known prefix like {', '.join(_KNOWN_EFFECTS_PREFIXES)}. "
                                f"If this is a custom prefix, document it in the plugin's README."
                            ),
                            plugin_id=self._extract_plugin_id(dec),
                        )
                    )

        # Check 2: __init__.py prohibition (AGENTS.md §5: one plugin per file).
        if path.name == "__init__.py" and plugin_decorators:
            findings.append(
                DoctorFinding(
                    code="DOC-PS-007",
                    severity="error",
                    owner=_OWNER_ADR,
                    message=(
                        f"@plugin decorator found in __init__.py "
                        f"(line {plugin_decorators[0].lineno})"
                    ),
                    remediation=(
                        "Per AGENTS.md §5: '每个 plugin 一个 .py 文件'. "
                        "Move @plugin to a dedicated file."
                    ),
                )
            )

        # Check 3: dual manifest (event_plugin_spec + plugin_spec).
        targets: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        targets.add(tgt.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets.add(node.target.id)
        if "event_plugin_spec" in targets and "plugin_spec" in targets:
            findings.append(
                DoctorFinding(
                    code="DOC-PS-002",
                    severity="error",
                    owner=_OWNER_ADR,
                    message="module declares both event_plugin_spec and plugin_spec (dual manifest)",
                    remediation=(
                        "Per ADR-0199 P0 单一入口: pick ONE manifest declaration. "
                        "events/{sinks,publishers,subscribers} use event_plugin_spec; "
                        "other plugins use @plugin(...)."
                    ),
                )
            )

        return DoctorReport.from_findings(subject, findings)

    @staticmethod
    def _find_plugin_decorators(tree: ast.AST) -> list[ast.Call]:
        """Find all @plugin(...) decorator calls in the module."""
        out: list[ast.Call] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if (
                        isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Name)
                        and dec.func.id == "plugin"
                    ):
                        out.append(dec)
        return out

    @staticmethod
    def _kwarg_names(call: ast.Call) -> set[str]:
        return {kw.arg for kw in call.keywords if kw.arg is not None}

    @staticmethod
    def _extract_kwarg_value(call: ast.Call, name: str) -> ast.expr | None:
        for kw in call.keywords:
            if kw.arg == name:
                return kw.value
        return None

    @staticmethod
    def _extract_plugin_id(call: ast.Call) -> str | None:
        """Try to extract the plugin_id kwarg value as a string literal."""
        for kw in call.keywords:
            if (
                kw.arg in {"id", "plugin_id"}
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                return kw.value.value
        return None

    @staticmethod
    def _check_effects(value: ast.expr | None) -> list[str]:
        """Return list of effect strings that don't match a known prefix.

        Static best-effort: handles tuple/list of string constants only.
        Variables, names, calls, and other non-literal expressions are
        silently ignored (the doctor pass is intentionally pessimistic —
        unknown shapes contribute zero findings rather than false positives).
        """
        if value is None:
            return []
        unknown: list[str] = []
        if isinstance(value, (ast.Tuple, ast.List)):
            for elt in value.elts:
                if (
                    isinstance(elt, ast.Constant)
                    and isinstance(elt.value, str)
                    and not any(elt.value.startswith(prefix) for prefix in _KNOWN_EFFECTS_PREFIXES)
                ):
                    unknown.append(elt.value)
        return unknown


__all__ = ("SinglePluginDoctor",)
