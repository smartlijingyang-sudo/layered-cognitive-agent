"""Contract tests for state-reflection elimination (ADR-0220 §闸门 5 + §14).

Three grep-style checks enforced via ``git grep`` (the ADR §14 canonical
mechanism — not AST or static import analysis). Each test counts hits in
the current working tree (which includes any dirty diff) and asserts the
count must be zero.

If a dirty diff re-introduces a ``getattr(state, "_xxx_ref", ...)`` call
or a ``runtime().inject(...)`` seam-theft, this test fails immediately
and surfaces the exact path. The tests therefore act as a pre-merge
guardrail on ADR-0220 §5, §8 and §14 acceptance criteria.

Three greps enforced here (out of the eleven listed in §14 — the three
that block ADR-0220 §闸门 5 and §闸门 9):

1. ``getattr(state, "_"`` — reflection read on ``AgentState`` private attrs.
2. ``_file_store_ref|_sandbox_ref|_skill_store_ref|_machine_resolver_ref|_search_ref``
   inside ``lca/contracts/`` — those attrs must not leak into the contracts
   layer at all.
3. ``runtime().inject(`` inside ``lca/plugins/`` — Cordis-private seam theft
   forbidden by ADR-0220 §8 / AGENTS.md plugin hard constraints.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ADR-0220 §14 grep signature #1: state-private reflection must be zero.
STATE_REFLECTION_PATTERN = re.compile(r'getattr\(state,\s*"_')

# ADR-0220 §14 grep signature #2: the 5 seam refs must not exist in contracts.
STATE_REF_ATTRS_PATTERN = re.compile(
    r"_file_store_ref|_sandbox_ref|_skill_store_ref|_machine_resolver_ref|_search_ref"
)

# ADR-0220 §14 grep signature #3: Cordis-private inject bypass must be zero.
RUNTIME_INJECT_PATTERN = re.compile(r"runtime\(\)\.inject\(")


_COMMENT_LINE = re.compile(r"^[^:]+:\d+:\s*#")


def _git_grep(pattern: re.Pattern[str], path: str) -> tuple[int, list[str]]:
    """Run ``git grep -nE <pattern> <path>`` and return ``(count, matches)``.

    The ADR §14 explicitly mandates ``git grep`` as the verification tool;
    AST or import inspection is not equivalent because grep catches string
    literals and dynamic construction that static analysis misses.

    Comment-prefixed lines (those starting with ``#`` after the
    ``path:lineno:`` prefix) are filtered out so that documentation /
    ADR-cross-reference notes are not mistaken for active code. A line
    inside a docstring that mentions the pattern is similarly not a
    runtime seam call.
    Returns ``(0, [])`` if the path is missing or has no tracked files.
    """
    proc = subprocess.run(  # noqa: S603 - inputs are static; ruff S607 (partial path) waived: git on PATH
        ["git", "grep", "-nE", pattern.pattern, path],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # git grep exits 1 when there are no matches — that is the success case.
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"git grep failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    output = proc.stdout
    if not output:
        return 0, []
    matches = [
        line
        for line in output.splitlines()
        if line.strip() and not _COMMENT_LINE.match(line)
    ]
    return len(matches), matches


class TestStateReflectionElimination:
    """ADR-0220 §闸门 5 — ``AgentState`` 不持 ref, ``reasoner.py`` 不反射读."""

    def test_no_state_reflection(self) -> None:
        """§14 grep #1: ``git grep -nE 'getattr\\(state, "_' lca/`` must be 0.

        Any positive count means a reflection read on a ``AgentState``
        private attr slipped back in. ``reasoner.py:300-305`` used to
        contain six such reads; this guard prevents regression.
        """
        count, matches = _git_grep(STATE_REFLECTION_PATTERN, "lca/")
        assert count == 0, (
            "ADR-0220 §闸门 5 violated: found "
            f"{count} reflection read(s) on AgentState private attrs in lca/. "
            "Expected zero. Offending lines:\n"
            + "\n".join(matches[:20])
        )

    def test_no_xxx_ref_attributes_in_state_source(self) -> None:
        """§14 grep #2: 5 ``_xxx_ref`` attributes must not be declared in contracts.

        The five attrs (``_file_store_ref`` / ``_sandbox_ref`` /
        ``_skill_store_ref`` / ``_machine_resolver_ref`` / ``_search_ref``)
        were seam containers on ``AgentState`` (ADR-0220 §2.2). They must
        not reappear in ``lca/contracts/`` — neither in the schema nor in
        any helper.
        """
        count, matches = _git_grep(STATE_REF_ATTRS_PATTERN, "lca/contracts/")
        assert count == 0, (
            "ADR-0220 §闸门 5 violated: "
            f"found {count} seam-ref attribute(s) declared in lca/contracts/. "
            "Expected zero (AgentState must not carry capability refs). "
            "Offending lines:\n"
            + "\n".join(matches[:20])
        )

    def test_no_seam_theft_in_reasoner_provider(self) -> None:
        """§14 grep #3: ``runtime().inject(`` is forbidden under ``lca/plugins/``.

        ADR-0220 §8 / §闸门 9: ``reasoner_provider.setup`` used to call
        ``runtime().inject(\"tools\")`` to bypass the Cordis ``requires=``
        manifest. Any plugin still using it is violating the contract.
        """
        count, matches = _git_grep(RUNTIME_INJECT_PATTERN, "lca/plugins/")
        assert count == 0, (
            "ADR-0220 §闸门 9 violated: "
            f"found {count} Cordis-private seam-theft call(s) under lca/plugins/. "
            "Expected zero (plugins must declare dependencies via manifest "
            "requires=, never via runtime().inject()). Offending lines:\n"
            + "\n".join(matches[:20])
        )


