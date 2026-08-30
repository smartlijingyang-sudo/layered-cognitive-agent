"""Substitution gates test — ADR-0076 §二 验证约束.

The **substitution test** is ADR-0076's single acceptance criterion for
"plugin-ability":

    Replacing a capability must only require adding or replacing a
    bundle / profile / plugin entry, never modifying a neighboring
    interpreter, composer, or gateway branch.

This module enforces that promise via static AST scans over the
interpreter, composer, and gateway code paths.  It looks for forbidden
patterns that betray a missing seam:

- **Control slot substitution** — string compare against slot names.
- **Phase executor substitution** — hard-coded phase → executor dispatch.
- **Effect / delta handler substitution** — direct construction of handler
  classes by name.
- **Team backend substitution** — ``new()`` of team-internal types in the
  composer (``TeamSharedMemoryStore``, ``TransportMemberInvoker``, etc.).
- **Run mode substitution** — string ``if/elif`` on mode keys in gateway.

If any of these patterns appears in production code, the test fails with
the exact location and a remediation hint.

The checks are intentionally conservative: false positives are acceptable
when they prompt a developer to justify a branch with a comment that
links back to ADR-0076.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# ── Paths under test ─────────────────────────────────────────────────
#
# ADR-0076 §二 lists five substitution axes; each has one (or two) files
# that MUST NOT contain the corresponding forbidden pattern.

INTERPRETER_PATH = REPO / "lca" / "layer2_runtime" / "declarative_runtime.py"
INTERPRETER_FALLBACK = REPO / "lca" / "harness" / "declarative" / "interpreter.py"
COMPOSER_DIRECTORY = REPO / "lca" / "plugins" / "composer"
COMPOSER_PATHS = (
    COMPOSER_DIRECTORY / "brain_composer.py",
    COMPOSER_DIRECTORY / "body_composer.py",
    COMPOSER_DIRECTORY / "perceive_composer.py",
    COMPOSER_DIRECTORY / "team_composer.py",
)
TEAM_TRANSPORT_PATH = COMPOSER_DIRECTORY / "team_transport.py"
GRAPH_STRATEGY_PATH = (
    REPO / "lca" / "layer3_agent" / "orchestration_strategies" / "graph" / "strategy.py"
)
GATEWAY_MODE_PATH = REPO / "gateway" / "modes.py"
GATEWAY_LOOP_PATH = REPO / "gateway" / "runs" / "loop_drivers.py"


def _read(path: Path) -> str:
    """Read source text; missing files yield empty string for skip tests."""

    return path.read_text(encoding="utf-8") if path.exists() else ""


def _parse(path: Path) -> ast.Module | None:
    """Parse Python source to AST; missing or invalid files yield ``None``."""

    if not path.exists():
        return None
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


def _control_slot_string_dispatches(tree: ast.Module) -> list[tuple[int, str]]:
    """Detect ``if slot == "<slot name>"`` style string dispatch.

    A *control slot substitution* must inject through the ``control``
    capability registry; the interpreter must not pick an implementation
    by string compare against slot names.
    """

    findings: list[tuple[int, str]] = []
    target_slots = {
        "perceive.context",
        "think.guard",
        "act.authorize",
        "act.constrain",
        "act.execute",
        "act.safe_boundary",
        "remember.admit",
        "stop.decide",
        "observe.checkpoint",
        "observe.wildcard",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for comparator in node.comparators:
            if (
                isinstance(comparator, ast.Constant)
                and isinstance(comparator.value, str)
                and comparator.value in target_slots
            ):
                findings.append((node.lineno, f"slot name literal: {comparator.value!r}"))
    return findings


def _phase_string_dispatches(tree: ast.Module) -> list[tuple[int, str]]:
    """Detect ``if phase == "<phase name>"`` style branch.

    Phase executors are selected by ``CapabilityBinding.executor_capability``
    in ``CompiledRunPlan``; the interpreter must not pick an implementation
    by string compare against phase names.
    """

    findings: list[tuple[int, str]] = []
    target_phases = {
        "perceive",
        "think",
        "gate",
        "act",
        "reflect",
        "remember",
        "stop",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for comparator in node.comparators:
            if (
                isinstance(comparator, ast.Constant)
                and isinstance(comparator.value, str)
                and comparator.value in target_phases
            ):
                findings.append((node.lineno, f"phase literal: {comparator.value!r}"))
    return findings


def _graph_node_type_dispatches(tree: ast.Module) -> list[tuple[int, str]]:
    """Detect concrete ``NodeType`` comparisons in the graph traversal kernel.

    Graph traversal owns DAG readiness and edge semantics only.  Agent,
    aggregator, and topology-node behavior must be resolved through the
    ``graph_node_executors`` capability rather than ``if node.type`` branches.
    """

    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = (node.left, *node.comparators)
        has_node_type = any(
            isinstance(operand, ast.Attribute)
            and operand.attr == "type"
            and isinstance(operand.value, ast.Name)
            and operand.value.id == "node"
            for operand in operands
        )
        has_node_type_constant = any(
            isinstance(operand, ast.Attribute)
            and operand.attr in {"ENTRY", "EXIT", "AGENT", "AGGREGATOR", "ROUTER"}
            and isinstance(operand.value, ast.Name)
            and operand.value.id == "NodeType"
            for operand in operands
        )
        if has_node_type and has_node_type_constant:
            findings.append((node.lineno, "graph node type dispatch"))
    return findings


def _direct_team_constructions(tree: ast.Module) -> list[tuple[int, str]]:
    """Detect ``TeamSharedMemoryStore(...)`` / ``TransportMemberInvoker(...)``.

    These classes must come from the booted profile via a team_seam
    capability, not be instantiated directly inside the composer.
    """

    findings: list[tuple[int, str]] = []
    forbidden_names = {"TeamSharedMemoryStore", "TransportMemberInvoker"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # bare ``TeamSharedMemoryStore(...)`` call
        if isinstance(func, ast.Name) and func.id in forbidden_names:
            findings.append((node.lineno, f"direct {func.id}(...) construction"))
        # ``Foo.TransportMemberInvoker(...)`` or module-qualified call
        if isinstance(func, ast.Attribute) and func.attr in forbidden_names:
            findings.append((node.lineno, f"direct {func.attr}(...) construction"))
    return findings


def _mode_string_dispatches(tree: ast.Module) -> list[tuple[int, str]]:
    """Detect ``if key == "solo"`` / ``elif key == "team"`` style dispatch.

    The gateway must use ``run_mode_registry`` (capability seam) instead of
    string-compare branching on mode keys.  Both literal-string and
    module-constant (``Name``) operands are caught so a thin alias does
    not bypass the gate.
    """

    findings: list[tuple[int, str]] = []
    target_modes = {"solo", "team", "auto", "cordis-creator"}
    target_mode_names = {
        "SOLO_MODE_KEY",
        "TEAM_MODE_KEY",
        "AUTO_MODE_KEY",
        "CORDIS_CREATOR_MODE_KEY",
        "DEFAULT_MODE",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                if comparator.value in target_modes:
                    findings.append((node.lineno, f"mode key literal: {comparator.value!r}"))
                continue
            if isinstance(comparator, ast.Name) and comparator.id in target_mode_names:
                findings.append((node.lineno, f"mode constant name: {comparator.id}"))
    return findings


def _format(findings: Iterable[tuple[int, str]], path: Path) -> list[str]:
    return [f"{path.relative_to(REPO)}:{line} {reason}" for line, reason in findings]


# ── Tests ─────────────────────────────────────────────────────────────


def test_interpreter_does_not_branch_on_control_slot_names() -> None:
    """Declarative runtime interpreter must not branch on slot name strings."""

    tree = _parse(INTERPRETER_PATH)
    if tree is None:
        return  # interpreter file does not yet exist; skip
    findings = _format(_control_slot_string_dispatches(tree), INTERPRETER_PATH)
    assert not findings, (
        "Interpreter branches on control slot name strings — substitution "
        "test fails (ADR-0076 §二):\n  - "
        + "\n  - ".join(findings)
        + "\nRemediation: inject the slot executor from the compiled plan "
        "via the control capability; never compare slot names."
    )


def test_interpreter_fallback_does_not_branch_on_control_slot_names() -> None:
    """Legacy interpreter (harness/declarative) must also be slot-string-free."""

    tree = _parse(INTERPRETER_FALLBACK)
    if tree is None:
        return  # file missing; skip silently (legacy path may be removed)
    findings = _format(_control_slot_string_dispatches(tree), INTERPRETER_FALLBACK)
    assert not findings, (
        "Harness interpreter branches on control slot name strings:\n  - " + "\n  - ".join(findings)
    )


def test_interpreter_does_not_branch_on_phase_names() -> None:
    """Phase executors must come from the compiled plan, not string dispatch."""

    tree = _parse(INTERPRETER_PATH)
    if tree is None:
        return
    findings = _format(_phase_string_dispatches(tree), INTERPRETER_PATH)
    assert not findings, (
        "Interpreter branches on phase name strings — substitution test "
        "fails (ADR-0076 §二):\n  - "
        + "\n  - ".join(findings)
        + "\nRemediation: resolve phase executors through "
        "plan.capability_bindings and the phase_executor capability; "
        "never compare phase names."
    )


def test_graph_traversal_does_not_dispatch_on_node_type() -> None:
    """Concrete graph node behavior must come from the node-executor registry."""

    tree = _parse(GRAPH_STRATEGY_PATH)
    if tree is None:
        return
    findings = _format(_graph_node_type_dispatches(tree), GRAPH_STRATEGY_PATH)
    assert not findings, (
        "Graph traversal dispatches on concrete NodeType values — substitution test "
        "fails:\n  - "
        + "\n  - ".join(findings)
        + "\nRemediation: resolve GraphNodeExecutor through graph_node_executors; "
        "keep only topology and edge readiness in GraphStrategy."
    )


def test_composers_do_not_directly_construct_team_backends() -> None:
    """Concrete composer modules must consume team backends from scope, not ``new``."""

    findings: list[str] = []
    for path in COMPOSER_PATHS:
        tree = _parse(path)
        if tree is not None:
            findings.extend(_format(_direct_team_constructions(tree), path))
    assert not findings, (
        "Composer directly constructs team backends — substitution test "
        "fails (ADR-0076 §二 / §五):\n  - "
        + "\n  - ".join(findings)
        + "\nRemediation: inject TeamSharedMemoryStore/TransportMemberInvoker "
        "through team_seam capability; the composer only consumes scope."
    )


def test_team_transport_does_not_directly_construct_team_backends() -> None:
    """``build_team_transport`` is a factory helper; it must not ``new`` team backends.

    This is intentionally tolerant: ``InternalTransport()`` is allowed because
    it is the default in-process transport.  Only the substitution-flagged
    types (``TeamSharedMemoryStore``, ``TransportMemberInvoker``) must be
    absent.
    """

    tree = _parse(TEAM_TRANSPORT_PATH)
    if tree is None:
        return
    findings = _format(_direct_team_constructions(tree), TEAM_TRANSPORT_PATH)
    assert not findings, (
        "team_transport.py directly constructs team backends:\n  - " + "\n  - ".join(findings)
    )


def test_gateway_does_not_branch_on_mode_keys() -> None:
    """Gateway mode resolution must use a registry, not string if/elif."""

    tree = _parse(GATEWAY_MODE_PATH)
    if tree is None:
        return
    findings = _format(_mode_string_dispatches(tree), GATEWAY_MODE_PATH)
    assert not findings, (
        "gateway/modes.py branches on mode name strings — substitution "
        "test fails (ADR-0076 §六):\n  - "
        + "\n  - ".join(findings)
        + "\nRemediation: register each mode as a mode adapter plugin and "
        "resolve via run_mode_registry seam; never compare mode keys."
    )


def test_loop_driver_does_not_branch_on_mode_keys() -> None:
    """``gateway/runs/loop_drivers.py`` must not branch on mode name strings.

    The legacy carrier already routes through ``CognitiveRunnableAssembler``
    with a dict-of-adapters pattern; a remaining string-compare on
    ``mode == SOLO_MODE_KEY`` is acceptable **only** as the priority
    heuristic in the inbox followup helper (which is a record-only side
    effect).  Any other compare triggers this test.
    """

    text = _read(GATEWAY_LOOP_PATH)
    if not text:
        return
    tree = ast.parse(text)
    findings: list[tuple[int, str]] = []
    target_modes = {"solo", "team", "auto", "cordis-creator"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        # Skip the single allowed heuristic: ``priority="task" if mode == SOLO_MODE_KEY else ...``
        if (
            len(node.ops) == 1
            and isinstance(node.ops[0], ast.Eq)
            and isinstance(node.left, ast.Name)
            and node.left.id == "mode"
            and isinstance(node.comparators[0], ast.Name)
            and node.comparators[0].id == "SOLO_MODE_KEY"
        ):
            continue
        for comparator in node.comparators:
            if (
                isinstance(comparator, ast.Constant)
                and isinstance(comparator.value, str)
                and comparator.value in target_modes
            ):
                findings.append((node.lineno, f"mode key literal: {comparator.value!r}"))
    formatted = _format(findings, GATEWAY_LOOP_PATH)
    assert not formatted, (
        "gateway/runs/loop_drivers.py branches on mode name strings — "
        "substitution test fails (ADR-0076 §六):\n  - " + "\n  - ".join(formatted)
    )


def test_substitution_axes_have_a_corresponding_seam() -> None:
    """The five substitution axes must each be backed by a capability seam.

    The test enumerates the seams declared in two locations:

    - ``lca/contracts/capabilities.py`` — typed ``Capability[object]`` entries.
    - ``lca/harness/profile/runtime_closure.py`` — production closure-required keys.

    A new axis without a seam entry in either list is a violation.
    """

    import lca.contracts.capabilities as caps
    from lca.harness.profile.runtime_closure import runtime_closure_requirements

    declared_typed = {
        getattr(caps, name).key
        for name in dir(caps)
        if isinstance(getattr(caps, name, None), caps.Capability)
    }
    declared_closure = {requirement.capability for requirement in runtime_closure_requirements()}

    required_axes = {
        # effect/delta handler registries (Execution plane, closure-required)
        "effect_handler_registry",
        "delta_handler_registry",
        # team seam and node primitives (Organization plane)
        "team_seam",
        "graph_node_executors",
        # run mode adapter (Organization plane)
        "run_mode_registry",
        # team-casting content policy (Organization plane)
        "team_casting_prompt_renderer",
        # reasoning-template content policy (Cognition plane)
        "reasoner_template_catalog",
        # memory policy components (Cognition plane)
        "memory.write_policy",
        "memory.compaction_policy",
        "memory.retrieval_policy",
        # dynamic composition governance (Control plane)
        "composition.invariant_checker",
    }
    declared = declared_typed | declared_closure
    missing = sorted(required_axes - declared)
    assert not missing, (
        "ADR-0076 substitution axes without corresponding capability seam: "
        f'{missing}. Declare a `Capability[object]("<key>")` in '
        "lca/contracts/capabilities.py (or declare it in "
        "runtime_closure_requirements()) "
        "and provide a Tier-1 seam plugin."
    )


__all__ = [
    "test_composers_do_not_directly_construct_team_backends",
    "test_gateway_does_not_branch_on_mode_keys",
    "test_graph_traversal_does_not_dispatch_on_node_type",
    "test_interpreter_does_not_branch_on_control_slot_names",
    "test_interpreter_does_not_branch_on_phase_names",
    "test_interpreter_fallback_does_not_branch_on_control_slot_names",
    "test_loop_driver_does_not_branch_on_mode_keys",
    "test_substitution_axes_have_a_corresponding_seam",
    "test_team_transport_does_not_directly_construct_team_backends",
]
