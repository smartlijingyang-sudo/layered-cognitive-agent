"""Composer consumes compiled capability — ADR-0076 §五 验证约束.

Composers must consume capabilities through the booted ``Context`` and the
``CompiledRunPlan``.  They must not ``new()`` concrete implementations
inline.  This module is the public acceptance path listed in the ADR's
验证约束 section:

    tests/composer/test_composer_consumes_compiled_capability.py: composer
    不直接构造具体实现

The tests cover five invariants:

1. ``BodyComposer`` consumes the action handler registry plus the Body and
   Hook registry factory keys declared on ``AgentSpec`` from scope.
2. ``PerceiveComposer`` resolves the State-cluster ``stop_policy`` and
   contributes it only to the stop phase; ``AgentSpec`` has no stop-policy axis.
3. ``TeamComposer`` reads the ``team_seam`` capability instead of calling
   ``TeamSharedMemoryStore(...)`` / ``TransportMemberInvoker(...)`` /
   ``build_team_transport(...)`` directly.
4. The compiled capability surface is the only seam: there are no other
   hidden inline constructions.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from lca.contracts.capabilities import (
    OBSERVABILITY,
    STRATEGIES,
    TEAM_SEAM,
)
from lca.contracts.harness.composition.composer import AgentCompositionRequest
from lca.contracts.protocols.journal.spec import AgentSpec
from lca.plugins.collaboration.team_communication_seam import (
    DefaultTeamCommunicationAssembler,
)
from lca.plugins.collaboration.team_seam_seam import TeamSeam, TeamSeamFactory
from lca.plugins.collaboration.team_shared_memory_seam import DefaultTeamSharedMemoryResolver

REPO = Path(__file__).resolve().parents[2]
COMPOSER_DIRECTORY = REPO / "lca" / "plugins" / "composer"
BRAIN_COMPOSER_PATH = COMPOSER_DIRECTORY / "think" / "brain_composer.py"
BODY_COMPOSER_PATH = COMPOSER_DIRECTORY / "act" / "body_composer.py"
PERCEIVE_COMPOSER_PATH = COMPOSER_DIRECTORY / "perceive" / "perceive_composer.py"
TEAM_COMPOSER_PATH = COMPOSER_DIRECTORY / "collaboration" / "team_composer.py"
COMPOSER_PATHS = (
    BRAIN_COMPOSER_PATH,
    BODY_COMPOSER_PATH,
    PERCEIVE_COMPOSER_PATH,
    TEAM_COMPOSER_PATH,
)


def _read_composer_source() -> str:
    """Read the concrete plane modules, not the compatibility facade."""

    return "\n".join(path.read_text(encoding="utf-8") for path in COMPOSER_PATHS)


def _composer_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _default_team_seam_factory() -> TeamSeamFactory:
    """Build the explicit default Team backend pair for seam unit tests."""

    return TeamSeamFactory(
        shared_memory_resolver=DefaultTeamSharedMemoryResolver(),
        communication_assembler=DefaultTeamCommunicationAssembler(),
    )


def test_agent_composition_request_exposes_only_declared_fields() -> None:
    """Composition callers must name the field they consume explicitly."""

    request = AgentCompositionRequest(spec=SimpleNamespace(body="simple"))

    assert request.spec.body == "simple"
    with pytest.raises(AttributeError, match="body"):
        _ = request.body


def _class_methods(tree: ast.Module, class_name: str) -> list[ast.FunctionDef]:
    """Return the methods of ``class_name`` in ``tree`` (top-level only)."""

    methods: list[ast.FunctionDef] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            methods.extend(item for item in node.body if isinstance(item, ast.FunctionDef))
    return methods


# ── 1. BodyComposer consumes action_handler_registry from scope ────────


def test_body_composer_injects_action_handler_registry_from_scope() -> None:
    """BodyComposer must inject ``action_handler_registry`` through the scope.

    The static check confirms the composer calls ``require_capability(scope, ACTION_HANDLERS.key)``
    (mandatory, no ``_try_inject`` fallback) before consulting the action catalog.
    """

    source = _read_composer_source()
    assert "ACTION_HANDLERS.key" in source, (
        "BodyComposer must consume action_handler_registry from scope (ADR-0076 §五)."
    )
    assert "require_capability(scope, ACTION_HANDLERS.key)" in source, (
        "BodyComposer must consume action_handler_registry via require_capability "
        "(mandatory injection, no fallback path)."
    )


def test_agent_spec_body_field_is_overridable() -> None:
    """``AgentSpec.body`` declares the Body factory key with a stable default."""

    assert AgentSpec.__dataclass_fields__["body"].default == "simple"
    assert AgentSpec.__dataclass_fields__["body"].type == "str"


def test_body_composer_reads_body_key_from_spec() -> None:
    """Body selection belongs to the plan-bound specification, not the composer.

    The ``bodies`` registry is a real seam only if a profile can choose its
    registered implementation.  ``getattr`` would silently recreate a
    fallback outside the immutable AgentSpec contract.
    """

    source = _read_composer_source()
    assert "body_key = request.spec.body" in source, (
        "BodyComposer must read the body factory key from request.spec."
    )
    assert "body_factory.create(\n                body_key," in source, (
        "BodyComposer must forward the AgentSpec body key to the bodies seam."
    )
    assert 'getattr(request.spec, "body"' not in source, (
        "BodyComposer must not recreate a body fallback with getattr."
    )


def test_agent_spec_hooks_field_is_overridable() -> None:
    """``AgentSpec.hooks`` declares the Hook registry factory key."""

    assert AgentSpec.__dataclass_fields__["hooks"].default == "simple"
    assert AgentSpec.__dataclass_fields__["hooks"].type == "str"


def test_body_composer_reads_hook_key_from_spec() -> None:
    """Hook registry selection must remain plan-bound and explicit."""

    source = _read_composer_source()
    assert "hook_key = request.spec.hooks" in source, (
        "BodyComposer must read the hook registry key from request.spec."
    )
    assert "hooks = hook_factory.create(hook_key)" in source, (
        "BodyComposer must forward the AgentSpec hook key to the hooks seam."
    )
    assert 'getattr(request.spec, "hooks"' not in source, (
        "BodyComposer must not recreate a hook registry fallback with getattr."
    )


def test_body_composer_does_not_call_build_default_action_registry() -> None:
    """BodyComposer must not call ``build_default_action_registry``.

    ADR-0076 §五 forbids the BodyComposer from calling
    ``build_default_action_registry`` — the action catalog must come from
    the compiled plan authority (``request.allowed_actions``) and the
    scope-injected ``action_handler_registry``.
    """

    source = _read_composer_source()
    assert "build_default_action_registry" not in source, (
        "BodyComposer must not call build_default_action_registry (ADR-0076 §五). "
        "Use the scope-injected action_handler_registry and request.allowed_actions."
    )


def test_body_composer_consumes_allowed_actions_from_request() -> None:
    """BodyComposer must read ``allowed_actions`` from the request, not a static table.

    ADR-0076 §五 requires the action catalog to come from the
    CompiledRunPlan authority data; the request carries
    ``allowed_actions`` / ``forbidden_actions`` derived from
    :class:`ActionAuthorityPlan`.
    """

    source = _read_composer_source()
    assert "request.allowed_actions" in source, (
        "BodyComposer must consume allowed_actions from request (plan authority)."
    )
    assert "request.forbidden_actions" in source, (
        "BodyComposer must consume forbidden_actions from request (plan authority)."
    )


def test_agent_assembly_rejects_a_plan_without_action_authority(monkeypatch) -> None:
    """Production assembly must not translate missing plan authority into no actions."""
    from unittest.mock import MagicMock

    from lca.plugins.composer.composition import plan_binding
    from lca.plugins.composer.composition.agent_assembly import PlanBoundAgentAssembler
    from lca.plugins.composer.composition.plan_binding import BindPlanError

    plan = MagicMock()
    plan.action_authority = None
    monkeypatch.setattr(plan_binding, "compiled_plan_from_scope", lambda _scope: plan)

    with pytest.raises(BindPlanError, match="action_authority"):
        PlanBoundAgentAssembler().assemble_agent(MagicMock(), scope=SimpleNamespace())


# ── 2. PerceiveComposer contributes a local StopPolicy ─────────────────


def test_perceive_composer_contributes_state_stop_policy_locally() -> None:
    """StopPolicy is resolved from State and exposed only to the stop phase."""

    source = _read_composer_source()
    assert "resolve_stop_policy(scope=scope)" in source
    assert 'phase_capabilities={"stop_policy": stop_policy}' in source
    assert "stop_rule=" not in source
    assert "request.spec.stop_rule" not in source


def test_agent_spec_has_no_top_level_stop_policy_axis() -> None:
    """Termination behavior is selected by the State-cluster plugin, not AgentSpec."""

    assert "stop_rule" not in AgentSpec.__dataclass_fields__
    assert "stop_policy" not in AgentSpec.__dataclass_fields__


def test_perceive_composer_does_not_reintroduce_stop_policy_factory_selection() -> None:
    """The composer must not select a named policy or construct one inline."""

    tree = _composer_ast(PERCEIVE_COMPOSER_PATH)
    methods = _class_methods(tree, "PerceiveComposer")
    compose_agent = next((m for m in methods if m.name == "compose_agent"), None)
    assert compose_agent is not None, "PerceiveComposer.compose_agent missing"

    source = ast.unparse(compose_agent)
    assert ".create(" not in source
    assert '"default"' not in source


# ── 3. TeamComposer reads team_seam instead of inline construction ─────


def test_team_composer_consumes_team_seam() -> None:
    """TeamComposer must consume ``TEAM_SEAM`` from scope, not construct inline."""

    source = TEAM_COMPOSER_PATH.read_text(encoding="utf-8")
    assert "TEAM_SEAM" in source, "TeamComposer must declare the TEAM_SEAM dependency."
    assert "require_capability(scope, TEAM_SEAM.key)" in source, (
        f"TeamComposer must consume {TEAM_SEAM.key!r} from scope (ADR-0076 §五)."
    )
    assert "seam_factory" in source, (
        "TeamComposer must name the team_seam factory explicitly so a "
        "profile can replace the implementation by registering a different "
        "TEAM_SEAM provider."
    )


def test_team_composer_assembles_each_member_once() -> None:
    """Shared-memory resolution must precede the one and only member assembly pass."""

    tree = _composer_ast(TEAM_COMPOSER_PATH)
    team_composer = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "TeamComposer"
    )
    member_calls = [
        call
        for call in ast.walk(team_composer)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "assemble_member"
    ]

    assert "resolve_shared_memory" in _read_composer_source()
    assert len(member_calls) == 1, (
        "TeamComposer must resolve shared memory before composing members, not "
        "rebuild members after the Team seam is closed."
    )


def test_team_composer_passes_resolved_store_to_one_member_assembly_pass() -> None:
    """A Team member receives the seam-resolved store during its only assembly pass."""

    from lca.contracts.models.team.team_coordination import Pipeline
    from lca.contracts.protocols.journal.spec import TeamSpec
    from lca.plugins.composer.collaboration.team_composer import TeamComposer
    from tests.support.agent_specs import make_spec

    class _RecordingAssembler:
        def __init__(self) -> None:
            self.member_stores: list[object | None] = []

        def assemble_member(self, spec, *, shared_store, observability, scope):
            del observability, scope
            self.member_stores.append(shared_store)
            return SimpleNamespace(role_profile=SimpleNamespace(role=spec.profile.role))

        def assemble_lead(self, spec, *, transport, mandate, observability, scope):
            del spec, transport, mandate, observability, scope
            raise AssertionError("Pipeline governance must not assemble a lead")

    class _RecordingTeamSeamFactory:
        def __init__(self) -> None:
            self.shared_store = object()
            self.build_arguments: tuple[object, tuple[object, ...], object | None] | None = None

        def resolve_shared_memory(self, spec):
            del spec
            return self.shared_store

        def build(self, spec, *, members, shared_memory):
            self.build_arguments = (spec, members, shared_memory)
            return SimpleNamespace(
                shared_memory=shared_memory,
                transport=object(),
                invoker=object(),
            )

    class _Strategies:
        def create(self, key, assembly):
            return SimpleNamespace(key=key, assembly=assembly)

    class _Scope:
        def __init__(self, seam_factory) -> None:
            self._capabilities = {
                TEAM_SEAM.key: seam_factory,
                STRATEGIES.key: _Strategies(),
                OBSERVABILITY.key: object(),
            }

        def inject(self, key):
            return self._capabilities[key]

    factory = _RecordingTeamSeamFactory()
    assembler = _RecordingAssembler()
    spec = TeamSpec(
        members=(make_spec("member-a", object()), make_spec("member-b", object())),
        governance=Pipeline(),
        shared_memory_layers=("semantic",),
    )

    graph = TeamComposer(assembler).compose_team(spec, _Scope(factory))

    assert assembler.member_stores == [factory.shared_store, factory.shared_store]
    assert factory.build_arguments is not None
    _, built_members, built_store = factory.build_arguments
    assert built_members == graph.members
    assert built_store is factory.shared_store


def test_team_composer_does_not_inline_team_backends() -> None:
    """``TeamSharedMemoryStore`` / ``TransportMemberInvoker`` must not appear in the composer.

    The team_seam factory owns those constructions; the composer only
    consumes the resulting ``TeamSeam`` object.
    """

    source = _read_composer_source()
    forbidden_substrings = (
        "TeamSharedMemoryStore(",
        "TransportMemberInvoker(",
        "build_team_transport(",
    )
    findings = [token for token in forbidden_substrings if token in source]
    assert not findings, (
        "TeamComposer still constructs team backends inline: "
        f"{findings}. The team_seam seam owns construction (ADR-0076 §五)."
    )


def test_team_seam_factory_requires_profile_selected_backends() -> None:
    """The factory must not silently choose either Team backend collaborator."""

    with pytest.raises(TypeError, match="shared_memory_resolver"):
        TeamSeamFactory(communication_assembler=DefaultTeamCommunicationAssembler())
    with pytest.raises(TypeError, match="communication_assembler"):
        TeamSeamFactory(shared_memory_resolver=DefaultTeamSharedMemoryResolver())


def test_team_seam_plugin_consumes_shared_memory_resolver_from_scope() -> None:
    """The profile-selected resolver must be a required Team seam dependency."""

    module = REPO / "lca" / "plugins" / "collaboration" / "team_seam_seam.py"
    source = module.read_text(encoding="utf-8")
    assert "TEAM_SHARED_MEMORY_RESOLVER" in source
    assert (
        "shared_memory_resolver=require_capability(ctx, TEAM_SHARED_MEMORY_RESOLVER.key)" in source
    )


def test_team_seam_factory_produces_complete_seam() -> None:
    """The default ``TeamSeamFactory.build`` must return a fully populated seam."""

    from lca.contracts.models.team.team_coordination import Pipeline
    from lca.contracts.protocols.journal.spec import TeamSpec
    from lca.infrastructure.transport.agent_transport import InternalTransport

    factory = _default_team_seam_factory()
    spec = TeamSpec(
        members=(),
        governance=Pipeline(),
        shared_memory_layers=("semantic", "procedural"),
    )
    shared_memory = factory.resolve_shared_memory(spec)
    seam = factory.build(spec, members=(), shared_memory=shared_memory)
    assert isinstance(seam, TeamSeam)
    assert seam.shared_memory is shared_memory
    assert isinstance(seam.transport, InternalTransport)
    assert seam.invoker is not None
    assert seam.shared_memory is not None, (
        "team_seam must build TeamSharedMemoryStore when shared_memory_layers is non-empty."
    )


def test_team_seam_factory_returns_no_shared_memory_when_layers_empty() -> None:
    """When no shared layers are declared, ``shared_memory`` is ``None``."""

    from lca.contracts.models.team.team_coordination import Pipeline
    from lca.contracts.protocols.journal.spec import TeamSpec

    factory = _default_team_seam_factory()
    spec = TeamSpec(members=(), governance=Pipeline())
    shared_memory = factory.resolve_shared_memory(spec)
    seam = factory.build(spec, members=(), shared_memory=shared_memory)
    assert seam.shared_memory is shared_memory is None, (
        "team_seam must yield shared_memory=None when no shared_memory_layers declared."
    )


# ── 4. Compiled capability surface is the only seam ───────────────────


def test_composers_do_not_have_untracked_direct_constructions() -> None:
    """Composers must consume every team collaborator from the Team seam."""

    for path in COMPOSER_PATHS:
        tree = _composer_ast(path)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                func = sub.func
                # Detect bare ``Foo(...)`` calls.
                if isinstance(func, ast.Name) and func.id in {
                    "TeamSharedMemoryStore",
                    "TransportMemberInvoker",
                }:
                    raise AssertionError(
                        f"{node.name} constructs {func.id} inline — use the team_seam seam."
                    )


def test_composers_consume_action_scope_from_request() -> None:
    """BodyComposer must derive action scope from the request, not hard-code it."""

    source = _read_composer_source()
    assert "request.action_scope" in source, (
        "BodyComposer must consume action scope from the request, not a "
        "hard-coded constant (ADR-0076 §五)."
    )


def test_default_composers_expose_only_the_graph_operation_they_own() -> None:
    """The public composer interface must describe real, not hypothetical, work.

    Agent cluster composers participate only in ``bind_plan``; the collaboration
    composer participates only in ``bind_team``. Keeping unsupported methods
    absent prevents callers from restoring ``TypeError``-based routing.
    """

    from lca.contracts.harness.composition.composer import AgentGraphComposer, TeamGraphComposer
    from lca.plugins.composer.act.body_composer import BodyComposer
    from lca.plugins.composer.collaboration.team_composer import TeamComposer
    from lca.plugins.composer.composition.agent_assembly import (
        AgentAssemblyPort,
        PlanBoundAgentAssembler,
    )
    from lca.plugins.composer.perceive.perceive_composer import PerceiveComposer
    from lca.plugins.composer.think.brain_composer import BrainComposer

    for composer in (BrainComposer(), BodyComposer(), PerceiveComposer()):
        assert isinstance(composer, AgentGraphComposer)
        assert not hasattr(composer, "compose_team")
    assert AgentAssemblyPort in PlanBoundAgentAssembler.__bases__
    team_composer = TeamComposer(PlanBoundAgentAssembler())
    assert isinstance(team_composer, TeamGraphComposer)
    assert not hasattr(team_composer, "compose_agent")


__all__ = [
    "test_agent_spec_body_field_is_overridable",
    "test_agent_spec_has_no_top_level_stop_policy_axis",
    "test_agent_spec_hooks_field_is_overridable",
    "test_body_composer_injects_action_handler_registry_from_scope",
    "test_body_composer_reads_body_key_from_spec",
    "test_body_composer_reads_hook_key_from_spec",
    "test_composers_consume_action_scope_from_request",
    "test_composers_do_not_have_untracked_direct_constructions",
    "test_default_composers_expose_only_the_graph_operation_they_own",
    "test_perceive_composer_contributes_state_stop_policy_locally",
    "test_perceive_composer_does_not_reintroduce_stop_policy_factory_selection",
    "test_team_composer_assembles_each_member_once",
    "test_team_composer_consumes_team_seam",
    "test_team_composer_does_not_inline_team_backends",
    "test_team_composer_passes_resolved_store_to_one_member_assembly_pass",
    "test_team_seam_factory_produces_complete_seam",
    "test_team_seam_factory_returns_no_shared_memory_when_layers_empty",
]


def test_default_team_seam_factory_keeps_backend_decisions_independent() -> None:
    """Replacing one default Team backend decision must not affect the other.

    Shared memory is needed before member assembly, while transport and member
    invocation require completed members. The factory orchestrates both stages,
    but each stage has its own narrow test surface.
    """

    from lca.contracts.models.team.team_coordination import Pipeline
    from lca.contracts.protocols.journal.spec import TeamSpec

    class _SharedMemoryResolver:
        def __init__(self) -> None:
            self.calls: list[tuple[object, tuple[object, ...]]] = []
            self.store = object()

        def resolve(self, spec, *, shared_layers=()):
            self.calls.append((spec, shared_layers))
            return self.store

    class _CommunicationAssembler:
        def __init__(self) -> None:
            self.calls: list[tuple[object, tuple[object, ...]]] = []
            self.transport = object()
            self.invoker = object()

        def assemble(self, spec, *, members):
            self.calls.append((spec, members))
            return SimpleNamespace(transport=self.transport, invoker=self.invoker)

    resolver = _SharedMemoryResolver()
    communication = _CommunicationAssembler()
    factory = TeamSeamFactory(
        shared_memory_resolver=resolver,
        communication_assembler=communication,
    )
    spec = TeamSpec(members=(), governance=Pipeline(), shared_memory_layers=("semantic",))
    members = (SimpleNamespace(),)

    shared_memory = factory.resolve_shared_memory(spec)
    seam = factory.build(spec, members=members, shared_memory=shared_memory)

    assert resolver.calls == [(spec, ())]
    assert communication.calls == [(spec, members)]
    assert seam.shared_memory is resolver.store
    assert seam.transport is communication.transport
    assert seam.invoker is communication.invoker
