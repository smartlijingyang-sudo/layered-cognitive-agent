"""Tests for new ADR-0074 Protocol definitions."""

from lca.contracts.protocols.act.action_handler import (
    ActionHandler,
    ActionHandlerRegistry,
)
from lca.contracts.protocols.journal.artifact_closure import ArtifactClosure
from lca.contracts.protocols.gate.decision_classifier import DecisionClassifier
from lca.contracts.protocols.state.delta_handler import (
    DeltaHandler,
    DeltaHandlerRegistry,
)
from lca.contracts.protocols.act.effect_handler import (
    EffectHandler,
    EffectHandlerRegistry,
)
from lca.contracts.protocols.gate.gate_chain_composer import GateChainComposer


class TestDecisionClassifierProtocol:
    """DecisionClassifier Protocol tests."""

    def test_protocol_is_runtime_checkable(self):
        """Protocol should be runtime checkable."""
        assert hasattr(DecisionClassifier, "__protocol_attrs__")

    def test_protocol_has_classify_method(self):
        """Protocol should define classify method."""
        assert hasattr(DecisionClassifier, "classify")

    def test_runtime_check_accepts_structural_match(self):
        """isinstance() should accept any object with classify()."""

        class FakeClassifier:
            def classify(self, response):
                return None

        assert isinstance(FakeClassifier(), DecisionClassifier)

    def test_runtime_check_rejects_missing_method(self):
        """isinstance() should reject objects lacking classify()."""

        class Empty:
            pass

        assert not isinstance(Empty(), DecisionClassifier)


class TestEffectHandlerProtocols:
    """EffectHandler + EffectHandlerRegistry Protocol tests."""

    def test_effect_handler_is_runtime_checkable(self):
        assert hasattr(EffectHandler, "__protocol_attrs__")

    def test_effect_handler_registry_is_runtime_checkable(self):
        assert hasattr(EffectHandlerRegistry, "__protocol_attrs__")

    def test_effect_handler_has_handle_method(self):
        assert hasattr(EffectHandler, "handle")

    def test_effect_handler_registry_has_register_resolve_and_effect_snapshot(self):
        assert hasattr(EffectHandlerRegistry, "register")
        assert hasattr(EffectHandlerRegistry, "resolve")
        assert hasattr(EffectHandlerRegistry, "registered_effect_operations")

    def test_runtime_check_accepts_handler_match(self):
        """isinstance() should accept any object with async handle()."""

        class FakeHandler:
            async def handle(self, envelope, policy, capabilities):
                return None

        assert isinstance(FakeHandler(), EffectHandler)

    def test_runtime_check_accepts_registry_match(self):
        """isinstance() should accept any object with register() and resolve()."""

        class FakeRegistry:
            def register(self, operation, handler):
                pass

            def resolve(self, operation):
                return None

            def registered_effect_operations(self):
                return ()

        assert isinstance(FakeRegistry(), EffectHandlerRegistry)


class TestDeltaHandlerProtocols:
    """DeltaHandler + DeltaHandlerRegistry Protocol tests."""

    def test_delta_handler_is_runtime_checkable(self):
        assert hasattr(DeltaHandler, "__protocol_attrs__")

    def test_delta_handler_registry_is_runtime_checkable(self):
        assert hasattr(DeltaHandlerRegistry, "__protocol_attrs__")

    def test_delta_handler_has_apply_method(self):
        assert hasattr(DeltaHandler, "apply")

    def test_delta_handler_registry_has_register_resolve_and_delta_snapshot(self):
        assert hasattr(DeltaHandlerRegistry, "register")
        assert hasattr(DeltaHandlerRegistry, "resolve")
        assert hasattr(DeltaHandlerRegistry, "registered_delta_operations")

    def test_runtime_check_accepts_handler_match(self):
        """isinstance() should accept any object with apply()."""

        class FakeHandler:
            def apply(self, state, delta, reducer):
                return state

        assert isinstance(FakeHandler(), DeltaHandler)

    def test_runtime_check_accepts_registry_match(self):
        """isinstance() should accept any object with register() and resolve()."""

        class FakeRegistry:
            def register(self, operation, handler):
                pass

            def resolve(self, operation):
                return None

            def registered_delta_operations(self):
                return ()

        assert isinstance(FakeRegistry(), DeltaHandlerRegistry)


class TestActionHandlerProtocols:
    """ActionHandler + ActionHandlerRegistry Protocol tests."""

    def test_action_handler_is_runtime_checkable(self):
        assert hasattr(ActionHandler, "__protocol_attrs__")

    def test_action_handler_registry_is_runtime_checkable(self):
        assert hasattr(ActionHandlerRegistry, "__protocol_attrs__")

    def test_action_handler_has_create_method(self):
        assert hasattr(ActionHandler, "create")

    def test_action_handler_registry_has_register_and_resolve(self):
        assert hasattr(ActionHandlerRegistry, "register")
        assert hasattr(ActionHandlerRegistry, "resolve")

    def test_action_handler_registry_has_registered_method(self):
        """``ActionHandlerRegistry.registered`` lists registered action types (ADR-0076 §五)."""
        assert hasattr(ActionHandlerRegistry, "registered")

    def test_runtime_check_accepts_handler_match(self):
        """isinstance() should accept any object with create()."""

        class FakeHandler:
            def create(self, tool_registry, safe_executor, transport_registry):
                return None

        assert isinstance(FakeHandler(), ActionHandler)

    def test_runtime_check_accepts_registry_match(self):
        """isinstance() should accept any object with register() and resolve()."""

        class FakeRegistry:
            def register(self, action_type, handler):
                pass

            def resolve(self, action_type):
                return None

            def registered(self):
                return ()

        assert isinstance(FakeRegistry(), ActionHandlerRegistry)


class TestArtifactClosureProtocol:
    """ArtifactClosure Protocol tests."""

    def test_protocol_is_runtime_checkable(self):
        assert hasattr(ArtifactClosure, "__protocol_attrs__")

    def test_protocol_has_synthesize_method(self):
        assert hasattr(ArtifactClosure, "synthesize")

    def test_runtime_check_accepts_structural_match(self):
        """isinstance() should accept any object with synthesize()."""

        class FakeClosure:
            def synthesize(self, *, fallback=""):
                return "closure text"

        assert isinstance(FakeClosure(), ArtifactClosure)

    def test_runtime_check_rejects_missing_method(self):
        """isinstance() should reject objects lacking synthesize()."""

        class Empty:
            pass

        assert not isinstance(Empty(), ArtifactClosure)


class TestGateChainComposerProtocol:
    """GateChainComposer Protocol tests."""

    def test_protocol_is_runtime_checkable(self):
        assert hasattr(GateChainComposer, "__protocol_attrs__")

    def test_protocol_has_compose_method(self):
        assert hasattr(GateChainComposer, "compose")

    def test_runtime_check_accepts_structural_match(self):
        """isinstance() should accept any object with compose()."""

        class FakeComposer:
            def compose(self):
                return None

        assert isinstance(FakeComposer(), GateChainComposer)

    def test_runtime_check_rejects_missing_method(self):
        """isinstance() should reject objects lacking compose()."""

        class Empty:
            pass

        assert not isinstance(Empty(), GateChainComposer)
