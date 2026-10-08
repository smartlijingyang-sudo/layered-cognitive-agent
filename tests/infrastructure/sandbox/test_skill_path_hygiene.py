"""Path hygiene: the guest mount literal lives in exactly one place (todo-81).

Two halves:

A. Source: no ``"/mnt/data"`` string literal in ``lca/`` outside the
   explicit allowlist below. The mount name is defined once
   (``SANDBOX_MOUNT_ROOT``); every mapping goes through
   ``lca.infrastructure.sandbox.paths.SandboxPaths``. A new literal is how
   the next todo-79 starts — fail loudly instead.

B. Skills: skill bodies and prompt templates must not hardcode host paths.
   Guest-executed content may reference the agent namespace
   (``/mnt/data/...`` — the retained virtual name); anything else absolute
   is a defect unless the skill is declared host-side. Host-operator skills
   (they drive the operator's own machine, not a sandbox guest) are listed
   in ``_HOST_SIDE_SKILLS`` with reasons.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_MOUNT_LITERAL = "/mnt/data"

# file -> reason. Keep this list short; every entry is a place the mount
# name is *named*, never a place that *maps* it.
_SOURCE_ALLOWLIST = {
    "lca/contracts/models/core/execution/sandbox.py": "SSOT definition of SANDBOX_MOUNT_ROOT",
    "lca/contracts/models/core/execution/fingerprint.py": (
        "contract-layer workspace-root alias table (pure data, no path mapping)"
    ),
    "lca/plugins/tools/file_write.py": (
        "user-facing message documenting the guest contract (example path)"
    ),
}

_HOST_SIDE_SKILLS = {
    # skill dir name -> reason
    "machine-search": "host-operator skill: searches the operator's own machine (/home/lichao)",
    "last30days": "host-operator skill: browser/CDP automation on the host",
    "airtap-automation": "host-operator skill: host tooling paths",
}

_URL_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+")
# Only well-known host roots: URL path fragments (/slide), CLI subcommands
# (/agent) and doc-relative paths (/docs/...) are not host paths.
_HOST_ROOTS = r"(?:home|root|etc|var|opt|usr|srv|data|private|Users|tmp|mnt)"
_ABS_PATH_RE = re.compile(r"(?<![\w$:/])/" + _HOST_ROOTS + r"/[^\s`\"'<>(){}|\[\]]+")

# (skill path, lineno) -> reason. Documents the mapping; does not instruct
# execution against a hardcoded host path.
_SKILL_LINE_ALLOWLIST = {
    ("skills/editing-lca-compositions/SKILL.md", 112): (
        "documents the plane-aware LCA_AGENT_PRESETS_HOME env var "
        "(guest /mnt/data/.agent-presets vs host dir); the mechanism "
        "itself is env-var based"
    ),
    (".agent/skills/using-git-worktrees/SKILL.md", 190): (
        "illustrative example transcript output, not an instruction "
        "to use a hardcoded path"
    ),
}


def _docstring_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            doc = node.body[0].value
            ranges.append((doc.lineno, doc.end_lineno or doc.lineno))
    return ranges


def _code_literals_with_mount(path: Path) -> list[tuple[int, str]]:
    """(lineno, literal) for non-docstring string constants containing the mount."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    doc_ranges = _docstring_ranges(tree)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if _MOUNT_LITERAL in node.value and not any(
            start <= node.lineno <= end for start, end in doc_ranges
        ):
            hits.append((node.lineno, node.value.strip().splitlines()[0][:80]))
    return hits


def test_no_new_mount_literals_in_source() -> None:
    violations: list[str] = []
    for path in sorted((REPO_ROOT / "lca").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, literal in _code_literals_with_mount(path):
            if rel in _SOURCE_ALLOWLIST:
                continue
            violations.append(f"{rel}:{lineno}: {literal!r}")
    assert not violations, (
        "new \"/mnt/data\" literals outside the allowlist — reference "
        "SANDBOX_MOUNT_ROOT / SandboxPaths instead:\n" + "\n".join(violations)
    )


def _skill_paths() -> list[Path]:
    found: list[Path] = []
    for base in ("skills", ".agent/skills"):
        root = REPO_ROOT / base
        if root.is_dir():
            found.extend(sorted(root.rglob("SKILL.md")))
    return found


def _absolute_paths_in_text(text: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        scrubbed = _URL_RE.sub("", line)
        for match in _ABS_PATH_RE.finditer(scrubbed):
            candidate = match.group(0).rstrip(".,;:")
            if candidate.startswith("/mnt/data"):
                continue  # the agent namespace itself — allowed
            hits.append((lineno, candidate))
    return hits


def test_skills_do_not_hardcode_host_paths() -> None:
    violations: list[str] = []
    used_allowlist: set[tuple[str, int]] = set()
    for path in _skill_paths():
        skill_name = path.parent.name
        if skill_name in _HOST_SIDE_SKILLS:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for lineno, candidate in _absolute_paths_in_text(text):
            key = (rel, lineno)
            if key in _SKILL_LINE_ALLOWLIST:
                used_allowlist.add(key)
                continue
            violations.append(f"{rel}:{lineno}: {candidate}")
    assert not violations, (
        "hardcoded host paths in guest-facing skills — use the agent namespace "
        "(/mnt/data/...), a template variable, or declare the skill host-side "
        "with a reason:\n" + "\n".join(violations)
    )
    stale = set(_SKILL_LINE_ALLOWLIST) - used_allowlist
    assert not stale, f"stale skill line allowlist entries: {stale}"


def test_host_side_skill_allowlist_is_accurate() -> None:
    """The allowlist must name real skills; stale entries fail loudly."""
    seen = {p.parent.name for p in _skill_paths()}
    for name in _HOST_SIDE_SKILLS:
        assert name in seen, f"allowlisted host-side skill not found: {name}"
