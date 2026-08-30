"""Tests for new ADR-0074 Provider implementations."""

import pytest

from lca.cognition.body.tool_batch_execution import SafeToolBatchExecutionPolicy
from lca.plugins.providers.action_handlers import (
    DefaultActionHandlerRegistry,
    DelegateActionHandler,
    HandoffActionHandler,
    RespondActionHandler,
    UseToolActionHandler,
)
from lca.plugins.providers.artifact_closure import DefaultArtifactClosure
from lca.plugins.providers.decision_classifier import DefaultDecisionClassifier
from lca.plugins.providers.delta_handlers import (
    ActivationDeltaHandler,
    ArtifactClosureDeltaHandler,
    DefaultDeltaHandlerRegistry,
    ErrorDeltaHandler,
    MemoryDeltaHandler,
    PausedDeltaHandler,
    PerceptionDeltaHandler,
    ResumeDeltaHandler,
    SkillRouteDeltaHandler,
    StepDeltaHandler,
    StopDeltaHandler,
    TurnDeltaHandler,
)
from lca.plugins.providers.effect_handlers import (
    BodyActEffectHandler,
    InMemoryEffectHandlerRegistry,
    MemoryUpdateEffectHandler,
    register_default_effect_handlers,
)
from lca.plugins.providers.gate_chain_composer import DefaultGateChainComposer


class TestDefaultDecisionClassifier:
    """DefaultDecisionClassifier tests."""

    def test_implements_protocol(self):
        """Should implement DecisionClassifier Protocol."""
        from lca.contracts.protocols.decision_classifier import DecisionClassifier

        classifier = DefaultDecisionClassifier()
        assert isinstance(classifier, DecisionClassifier)

    def test_has_classify_method(self):
        """Should have classify method."""
        classifier = DefaultDecisionClassifier()
        assert hasattr(classifier, "classify")
        assert callable(classifier.classify)


class TestEffectHandlers:
    """EffectHandler implementation tests."""

    def test_body_act_handler_implements_protocol(self):
        """BodyActEffectHandler should implement EffectHandler Protocol."""
        from lca.contracts.protocols.effect_handler import EffectHandler

        handler = BodyActEffectHandler()
        assert isinstance(handler, EffectHandler)

    def test_memory_update_handler_implements_protocol(self):
        """MemoryUpdateEffectHandler should implement EffectHandler Protocol."""
        from lca.contracts.protocols.effect_handler import EffectHandler

        handler = MemoryUpdateEffectHandler()
        assert isinstance(handler, EffectHandler)

    def test_empty_registry_implements_protocol(self):
        """The seam-provided registry is a neutral EffectHandlerRegistry container."""
        from lca.contracts.protocols.effect_handler import EffectHandlerRegistry

        registry = InMemoryEffectHandlerRegistry()
        assert isinstance(registry, EffectHandlerRegistry)

    def test_default_handlers_are_registered_explicitly(self):
        """Provider-owned setup, not registry construction, selects standard behavior."""
        registry = InMemoryEffectHandlerRegistry()
        assert registry.resolve("body.act") is None
        register_default_effect_handlers(registry)
        assert isinstance(registry.resolve("body.act"), BodyActEffectHandler)
        assert isinstance(registry.resolve("memory.update"), MemoryUpdateEffectHandler)

    def test_registry_register_and_resolve(self):
        """Registry should register and resolve handlers by operation name."""
        registry = InMemoryEffectHandlerRegistry()
        handler = BodyActEffectHandler()
        registry.register("body.act", handler)
        resolved = registry.resolve("body.act")
        assert resolved is handler

    def test_registry_resolve_unknown_returns_none(self):
        """Registry should return None for unregistered operations."""
        registry = InMemoryEffectHandlerRegistry()
        resolved = registry.resolve("unknown.operation")
        assert resolved is None

    def test_registry_register_multiple_handlers(self):
        """Registry should store multiple handlers."""
        registry = InMemoryEffectHandlerRegistry()
        body_handler = BodyActEffectHandler()
        memory_handler = MemoryUpdateEffectHandler()
        registry.register("body.act", body_handler)
        registry.register("memory.update", memory_handler)

        assert registry.resolve("body.act") is body_handler
        assert registry.resolve("memory.update") is memory_handler

    def test_body_act_handler_has_handle_method(self):
        """BodyActEffectHandler should have handle method."""
        handler = BodyActEffectHandler()
        assert hasattr(handler, "handle")
        assert callable(handler.handle)

    def test_memory_update_handler_has_handle_method(self):
        """MemoryUpdateEffectHandler should have handle method."""
        handler = MemoryUpdateEffectHandler()
        assert hasattr(handler, "handle")
        assert callable(handler.handle)


class TestDeltaHandlers:
    """DeltaHandler implementation tests."""

    def test_step_handler_implements_protocol(self):
        """StepDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = StepDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_perception_handler_implements_protocol(self):
        """PerceptionDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = PerceptionDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_turn_handler_implements_protocol(self):
        """TurnDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = TurnDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_skill_route_handler_implements_protocol(self):
        """SkillRouteDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = SkillRouteDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_activation_handler_implements_protocol(self):
        """ActivationDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = ActivationDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_memory_handler_implements_protocol(self):
        """MemoryDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = MemoryDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_stop_handler_implements_protocol(self):
        """StopDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = StopDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_error_handler_implements_protocol(self):
        """ErrorDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = ErrorDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_resume_handler_implements_protocol(self):
        """ResumeDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = ResumeDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_artifact_closure_handler_implements_protocol(self):
        """ArtifactClosureDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = ArtifactClosureDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_paused_handler_implements_protocol(self):
        """PausedDeltaHandler should implement DeltaHandler Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandler

        handler = PausedDeltaHandler()
        assert isinstance(handler, DeltaHandler)

    def test_default_registry_implements_protocol(self):
        """DefaultDeltaHandlerRegistry should implement DeltaHandlerRegistry Protocol."""
        from lca.contracts.protocols.delta_handler import DeltaHandlerRegistry

        registry = DefaultDeltaHandlerRegistry()
        assert isinstance(registry, DeltaHandlerRegistry)

    def test_registry_has_all_11_handlers(self):
        """兼容性工厂应集中安装全部 11 个默认 Reducer 操作。"""
        registry = DefaultDeltaHandlerRegistry()

        for operation in [
            "step",
            "perception",
            "turn",
            "skill_route",
            "activation",
            "memory",
            "stop",
            "error",
            "resume",
            "artifact_closure",
            "paused",
        ]:
            assert registry.resolve(operation) is not None, f"Missing handler for {operation}"

    def test_registry_resolve_unknown_returns_none(self):
        """Registry should return None for unregistered operations."""
        registry = DefaultDeltaHandlerRegistry()
        resolved = registry.resolve("unknown")
        assert resolved is None

    def test_all_handlers_have_apply_method(self):
        """All delta handlers should have apply method."""
        handlers = [
            StepDeltaHandler(),
            PerceptionDeltaHandler(),
            TurnDeltaHandler(),
            SkillRouteDeltaHandler(),
            ActivationDeltaHandler(),
            MemoryDeltaHandler(),
            StopDeltaHandler(),
            ErrorDeltaHandler(),
            ResumeDeltaHandler(),
            ArtifactClosureDeltaHandler(),
            PausedDeltaHandler(),
        ]
        for handler in handlers:
            assert hasattr(handler, "apply"), f"{handler.__class__.__name__} missing apply method"
            assert callable(handler.apply), f"{handler.__class__.__name__}.apply not callable"


class TestActionHandlers:
    """ActionHandler implementation tests."""

    def test_respond_handler_implements_protocol(self):
        """RespondActionHandler should implement ActionHandler Protocol."""
        from lca.contracts.protocols.action_handler import ActionHandler

        handler = RespondActionHandler()
        assert isinstance(handler, ActionHandler)

    def test_use_tool_handler_implements_protocol(self):
        """UseToolActionHandler should implement ActionHandler Protocol."""
        from lca.contracts.protocols.action_handler import ActionHandler

        handler = UseToolActionHandler(SafeToolBatchExecutionPolicy())
        assert isinstance(handler, ActionHandler)

    def test_use_tool_handler_requires_explicit_batch_policy(self):
        """策略选择必须由 Profile 或兼容门面显式承担。"""

        with pytest.raises(TypeError, match="batch_execution_policy"):
            UseToolActionHandler(None)  # type: ignore[arg-type]

    def test_delegate_handler_implements_protocol(self):
        """DelegateActionHandler should implement ActionHandler Protocol."""
        from lca.contracts.protocols.action_handler import ActionHandler

        handler = DelegateActionHandler()
        assert isinstance(handler, ActionHandler)

    def test_handoff_handler_implements_protocol(self):
        """HandoffActionHandler should implement ActionHandler Protocol."""
        from lca.contracts.protocols.action_handler import ActionHandler

        handler = HandoffActionHandler()
        assert isinstance(handler, ActionHandler)

    def test_default_registry_implements_protocol(self):
        """DefaultActionHandlerRegistry should implement ActionHandlerRegistry Protocol."""
        from lca.contracts.protocols.action_handler import ActionHandlerRegistry

        registry = DefaultActionHandlerRegistry()
        assert isinstance(registry, ActionHandlerRegistry)

    def test_default_registry_has_all_builtin_handlers(self):
        """默认注册表应在 Provider 外提供完整的内置 action 集合。"""
        from lca.contracts.atoms.enums import ActionType

        registry = DefaultActionHandlerRegistry()

        for action_type in [
            ActionType.RESPOND,
            ActionType.USE_TOOL,
            ActionType.DELEGATE,
            ActionType.HANDOFF,
        ]:
            assert registry.resolve(action_type) is not None, f"Missing handler for {action_type}"

    def test_registry_resolve_unknown_returns_none(self):
        """Registry should return None for unregistered action types."""
        registry = DefaultActionHandlerRegistry()
        resolved = registry.resolve("unknown")
        assert resolved is None

    def test_all_handlers_have_create_method(self):
        """All action handlers should have create method."""
        handlers = [
            RespondActionHandler(),
            UseToolActionHandler(SafeToolBatchExecutionPolicy()),
            DelegateActionHandler(),
            HandoffActionHandler(),
        ]
        for handler in handlers:
            assert hasattr(handler, "create"), f"{handler.__class__.__name__} missing create method"
            assert callable(handler.create), f"{handler.__class__.__name__}.create not callable"


class TestDefaultArtifactClosure:
    """DefaultArtifactClosure tests."""

    def test_implements_protocol(self):
        """Should implement ArtifactClosure Protocol."""
        from lca.contracts.protocols.artifact_closure import ArtifactClosure

        closure = DefaultArtifactClosure()
        assert isinstance(closure, ArtifactClosure)

    def test_has_synthesize_method(self):
        """Should have synthesize method."""
        closure = DefaultArtifactClosure()
        assert hasattr(closure, "synthesize")
        assert callable(closure.synthesize)


class TestDefaultGateChainComposer:
    """DefaultGateChainComposer tests."""

    def test_implements_protocol(self):
        """Should implement GateChainComposer Protocol."""
        from lca.contracts.protocols.gate_chain_composer import GateChainComposer

        composer = DefaultGateChainComposer()
        assert isinstance(composer, GateChainComposer)

    def test_has_compose_method(self):
        """Should have compose method."""
        composer = DefaultGateChainComposer()
        assert hasattr(composer, "compose")
        assert callable(composer.compose)
