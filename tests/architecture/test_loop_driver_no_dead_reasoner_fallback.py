"""Loop driver must not silently reach into a Cordis ``reasoner`` capability.

Background (post-mortem of run_73a271fd9d21):
PR-C deleted the ``phase.think.reasoner.compose`` provider plugin and the
implicit ``BrainComposer`` ``reasoner`` publishing it relied on. The
``CognitiveRunDriver`` carrier fallback that called
``require_capability(ctx, "reasoner")`` survived the cleanup with only
docstring edits and is no longer backed by any producer. Every ``runs
create`` on the post-PR-C kernel failed on the first carrier hop with
``MissingCapabilityError: 'reasoner'``.

These guards pin the end state the PR-C close-out missed:

1. The dead fallback function ``_resolve_resolver_from_reasoner`` and its
   adapter ``_BoundReasonerResolver`` are no longer defined in the
   carrier loop-drivers module.
2. The driver no longer tries to recover by looking up any Cordis
   capability key (currently ``reasoner`` or ``llm_resolver``) when no
   ``llm_resolver`` is supplied at call time — the contract is that the
   runnable seam has to receive a resolver from its composition root.
3. The dependency on the deleted ``LlmResolver`` workaround is gone
   end-to-end: ``require_capability`` for ``reasoner`` / ``llm_resolver``
   must not appear in this module.

When this guard passes, the regression cannot recur silently: any future
PR that re-introduces a dead Cordis lookup in the driver will fail the
test before it reaches main.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOOP_DRIVERS_PATH = (
    REPO
    / "lca"
    / "plugins"
    / "transport"
    / "webserver"
    / "carrier"
    / "runs"
    / "execute"
    / "loop_drivers.py"
)

_DEAD_NAMES = frozenset({"_BoundReasonerResolver", "_resolve_resolver_from_reasoner"})
_DEAD_CAPABILITY_KEYS = frozenset({"reasoner", "llm_resolver"})


def _read_source() -> str:
    return LOOP_DRIVERS_PATH.read_text(encoding="utf-8")


def test_dead_reasoner_fallback_symbols_are_removed() -> None:
    """``_BoundReasonerResolver`` and ``_resolve_resolver_from_reasoner`` are gone.

    The dead fallback depended on a Cordis ``reasoner`` provider that PR-C
    deleted; the symbols themselves have no surviving caller.
    """
    tree = ast.parse(_read_source())
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    survivors = _DEAD_NAMES & defined
    assert not survivors, (
        "Dead reasoner-fallback symbols still defined in "
        f"{LOOP_DRIVERS_PATH.relative_to(REPO)}: {sorted(survivors)}. "
        "PR-C removed the only producer; the fallback must be deleted, "
        "not merely undocumented."
    )


def test_no_capability_lookup_for_reasoner_or_llm_resolver() -> None:
    """The driver never calls ``require_capability(ctx, "reasoner"|"llm_resolver")``.

    LLM selection is a profile-time decision; the carrier is the wrong
    place to invent a resolver. Any ``require_capability`` / ``ctx.require``
    with those keys would be the same dead branch in a different costume.
    """
    tree = ast.parse(_read_source())
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name) or func.id not in {"require_capability"}:
            continue
        if not node.args and not node.keywords:
            continue
        for arg in (*node.args, *(kw.value for kw in node.keywords)):
            if (
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and arg.value in _DEAD_CAPABILITY_KEYS
            ):
                findings.append((node.lineno, f"require_capability({arg.value!r})"))
    assert not findings, (
        "CognitiveRunDriver still resolves a capability the carrier must not "
        "own; remove the lookup so the resolver comes from the composition root:\n"
        + "\n".join(f"  line {ln}: {msg}" for ln, msg in findings)
    )


def test_no_module_docstring_or_comment_mentions_braincomposer_binds_reasoner() -> None:
    """Stale docstring that claims ``BrainComposer`` binds ``reasoner`` must be gone.

    The original fallback was justified by a comment saying the composer
    was the boot-time binding site. After PR-C that contract is false and
    the comment is misleading; if any code path still references the
    claim, the cleanup is incomplete.
    """
    text = _read_source()
    forbidden_phrases = (
        "BrainComposer is the only LLM-aware setup",
        "BrainComposer.compose_agent did not seed reasoner",
        "phase.think.reasoner.compose is the single boot-time",
        "phase.think.reasoner.compose.setup() did not run correctly",
    )
    leaks = [phrase for phrase in forbidden_phrases if phrase in text]
    assert not leaks, (
        "Stale BrainComposer/phase.think.reasoner.compose narration remains in "
        f"{LOOP_DRIVERS_PATH.relative_to(REPO)}: {leaks}. "
        "PR-C removed both the binding and the provider; the comments "
        "should not survive as future traps."
    )


__all__ = [
    "test_dead_reasoner_fallback_symbols_are_removed",
    "test_no_capability_lookup_for_reasoner_or_llm_resolver",
    "test_no_module_docstring_or_comment_mentions_braincomposer_binds_reasoner",
]
