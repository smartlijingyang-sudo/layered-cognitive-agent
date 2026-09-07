"""Behavioral tests for the HTTP ``RunRequest`` → ``RunIntent`` adapter.

The adapter under test
(``lca.application.runtime.adapters.intent_from_transport``) only reads
fields off its argument via attribute access, so tests use a tiny stub
dataclass with the same shape as the real ``RunRequest`` instead of
importing the live class (which pulls in the full transport wiring).
The stub mirrors the real ``RunRequest`` field surface:
``profile``, ``user_text``, ``mode``, ``session_id`` (note: not on the
real ``RunRequest`` — see ``test_session_id_is_always_none``),
``assistant_id``, ``attachment_ids``, ``prior_turns``, ``execution_target``,
``options``, ``device_id``, ``ctx``, ``agent``, ``plane``, ``extra_plane``,
``question``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.application.runtime.adapters.intent_from_transport import (
    run_request_to_intent,
)
from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.contracts.runtime.intent import RunIntent


@dataclass(frozen=True)
class StubAgentRef:
    """Stand-in for ``lca.plugins.transport.webserver.read.runs.identity.identity.AgentRef``."""

    agent_id: str
    name: str


@dataclass(frozen=True)
class StubRunRequest:
    """Minimal stand-in for the real ``RunRequest``.

    Mirrors the field surface the adapter reads via ``getattr`` /
    direct attribute access. The real class also carries ``ctx``,
    ``agent``, ``plane``, ``extra_plane`` and ``question`` — these are
    included to assert the adapter drops them per I-HPC-2.
    """

    profile: str
    user_text: str
    mode: str = "solo"
    assistant_id: str | None = None
    attachment_ids: tuple[str, ...] = ()
    prior_turns: tuple[ConversationTurn, ...] = ()
    execution_target: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    device_id: str = ""
    ctx: object = None
    agent: StubAgentRef | None = None
    plane: str = ""
    extra_plane: str = ""
    question: str = ""


def _request(**overrides: Any) -> StubRunRequest:
    """Build a minimal ``StubRunRequest`` with overrides."""
    base: dict[str, Any] = {
        "profile": "/profiles/sample.yaml",
        "user_text": "hello",
    }
    base.update(overrides)
    return StubRunRequest(**base)


# ── Minimal translation ──────────────────────────────────────────────


class TestMinimalTranslation:
    def test_minimal_translation(self) -> None:
        """Bare required fields produce a valid ``RunIntent`` with defaults."""
        intent = run_request_to_intent(_request())

        assert isinstance(intent, RunIntent)
        assert intent.profile_path == "/profiles/sample.yaml"
        assert intent.user_text == "hello"
        assert intent.mode == "solo"
        assert intent.surface == "http"
        assert intent.device_id == ""

    def test_default_surface_is_http(self) -> None:
        """Default surface when the caller omits the override is ``http``."""
        intent = run_request_to_intent(_request())
        assert intent.surface == "http"

    def test_session_id_is_always_none(self) -> None:
        """``RunIntent.session_id`` is always ``None`` from this adapter.

        The HTTP carrier does not own session identity (ADR-0199 §2.2.1);
        the facade generates it from ``compute_activation_ref`` inputs.
        ``RunRequest`` does not carry a ``session_id`` field; this test
        pins the contract regardless of any future wire addition.
        """
        intent = run_request_to_intent(_request())
        assert intent.session_id is None


# ── Carries scalar fields ────────────────────────────────────────────


class TestCarriesScalarFields:
    def test_carries_assistant_id(self) -> None:
        """``RunRequest.assistant_id`` non-empty → ``RunIntent.assistant_id``."""
        intent = run_request_to_intent(_request(assistant_id="asst_abc"))
        assert intent.assistant_id == "asst_abc"

    def test_carries_assistant_id_none(self) -> None:
        """``None`` on the request → ``None`` on the intent."""
        intent = run_request_to_intent(_request(assistant_id=None))
        assert intent.assistant_id is None

    def test_carries_assistant_id_empty_string_becomes_none(self) -> None:
        """Empty-string ``assistant_id`` (legacy default) is normalised to ``None``.

        The carrier treats empty string as "no binding"; the intent
        must match so the facade does not see a meaningless binding.
        """
        intent = run_request_to_intent(_request(assistant_id=""))
        assert intent.assistant_id is None

    def test_carries_device_id_from_request(self) -> None:
        """When the caller does NOT override, ``device_id`` comes from the request."""
        intent = run_request_to_intent(_request(device_id="dev-7"))
        assert intent.device_id == "dev-7"


# ── Attachment / prior-turns / options ───────────────────────────────


class TestAttachmentAndTurnsAndOptions:
    def test_carries_attachment_refs(self) -> None:
        """List of refs → tuple on the intent (RunIntent is ``frozen=True``)."""
        intent = run_request_to_intent(_request(attachment_ids=("att-1", "att-2", "att-3")))
        assert intent.attachment_ids == ("att-1", "att-2", "att-3")

    def test_empty_attachment_ids_handled(self) -> None:
        """``None`` or empty tuple on the request → empty tuple on the intent."""
        intent_none = run_request_to_intent(_request(attachment_ids=None))  # type: ignore[arg-type]
        assert intent_none.attachment_ids == ()

        intent_empty = run_request_to_intent(_request(attachment_ids=()))
        assert intent_empty.attachment_ids == ()

    def test_carries_prior_turns(self) -> None:
        """``ConversationTurn`` instances are forwarded unchanged."""
        turns = (
            ConversationTurn(role="user", content="earlier"),
            ConversationTurn(role="assistant", content="response"),
        )
        intent = run_request_to_intent(_request(prior_turns=turns))
        assert intent.prior_turns == turns

    def test_carries_options_as_dict(self) -> None:
        """``options`` dict is preserved verbatim on the intent."""
        opts = {"idempotency_key": "abc", "temperature": 0.4}
        intent = run_request_to_intent(_request(options=opts))
        assert dict(intent.options) == opts


# ── L0 surface must drop ctx / agent / plane / question ──────────────


class TestL0SurfaceContract:
    def test_drops_ctx_field(self) -> None:
        """``RunRequest.ctx`` MUST NOT reach ``RunIntent`` (I-HPC-2).

        ``ctx`` is a live carrier object owned by K3 boot; the activation
        closure does not carry it (per ADR-0199 §2.2.2). The intent
        has no field to carry ``ctx`` even if a caller wanted to.
        """
        sentinel = object()
        intent = run_request_to_intent(_request(ctx=sentinel))
        # No attribute named ``ctx`` on RunIntent; access would raise.
        assert not hasattr(intent, "ctx")
        # Confirm by checking the intent surface is exactly the contract.
        assert set(intent.__dataclass_fields__) == {
            "profile_path",
            "user_text",
            "mode",
            "session_id",
            "assistant_id",
            "attachment_ids",
            "prior_turns",
            "execution_target",
            "options",
            "surface",
            "device_id",
        }

    def test_drops_agent_plane_and_question(self) -> None:
        """``agent`` / ``plane`` / ``extra_plane`` / ``question`` are L0-only and dropped."""
        intent = run_request_to_intent(
            _request(
                agent=StubAgentRef(agent_id="solo", name="Solo"),
                plane="main",
                extra_plane="shadow",
                question="the legacy question field",
            )
        )
        # None of these become fields on RunIntent.
        forbidden_field_names = {"agent", "plane", "extra_plane", "question"}
        leaked = forbidden_field_names & set(intent.__dataclass_fields__)
        assert leaked == set()


# ── Surface and device_id overrides ──────────────────────────────────


class TestOverrides:
    def test_surface_override(self) -> None:
        """An explicit ``surface=`` argument wins over the default ``http``."""
        intent = run_request_to_intent(_request(), surface="test")
        assert intent.surface == "test"

    def test_device_id_override(self) -> None:
        """Explicit ``device_id=`` argument wins over the request's value."""
        intent = run_request_to_intent(_request(device_id="dev-request"), device_id="dev-override")
        assert intent.device_id == "dev-override"

    def test_device_id_override_empty_falls_back_to_request(self) -> None:
        """Empty-string override does NOT clobber the request's value."""
        intent = run_request_to_intent(_request(device_id="dev-request"), device_id="")
        assert intent.device_id == "dev-request"
