"""Behavioral tests for the CLI ``CliRunArgs`` → ``RunIntent`` adapter.

The adapter under test
(``lca.application.runtime.adapters.intent_from_cli``) translates the
parser-produced ``CliRunArgs`` carrier into the wire-agnostic
``RunIntent``. CLI runs always start fresh — there is no carrier of
conversation history at the CLI layer — so ``prior_turns`` is always
empty.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any

import pytest

from lca.application.runtime.adapters.intent_from_cli import (
    CliRunArgs,
    cli_args_to_intent,
)
from lca.contracts.runtime.intent import RunIntent

# ── Carrier shape ────────────────────────────────────────────────────


class TestCliRunArgsShape:
    def test_cli_run_args_is_dataclass(self) -> None:
        """``CliRunArgs`` is a dataclass (consumers rely on ``fields`` / ``asdict``)."""
        assert is_dataclass(CliRunArgs)

    def test_cli_run_args_is_frozen(self) -> None:
        """``CliRunArgs`` is frozen — mutation raises ``FrozenInstanceError``."""
        args = CliRunArgs(profile="/p.yaml", user_text="hi")
        with pytest.raises(FrozenInstanceError):
            args.profile = "/other.yaml"  # type: ignore[misc]

    def test_cli_run_args_has_required_fields(self) -> None:
        """The carrier exposes the fields the CLI parser (P1-13) needs to fill."""
        names = {f.name for f in fields(CliRunArgs)}
        assert {
            "profile",
            "user_text",
            "mode",
            "session_id",
            "assistant_id",
            "attachment_ids",
            "execution_target",
            "options",
            "device_id",
        } <= names


# ── Minimal translation ──────────────────────────────────────────────


class TestMinimalTranslation:
    def test_minimal_cli_translation(self) -> None:
        """Bare required args produce a valid ``RunIntent``."""
        args = CliRunArgs(profile="/profiles/agent.yaml", user_text="hi")
        intent = cli_args_to_intent(args)
        assert isinstance(intent, RunIntent)
        assert intent.profile_path == "/profiles/agent.yaml"
        assert intent.user_text == "hi"

    def test_defaults_mode_to_solo(self) -> None:
        """``CliRunArgs.mode`` defaults to ``solo`` when the parser omits it."""
        args = CliRunArgs(profile="/p.yaml", user_text="hi")
        intent = cli_args_to_intent(args)
        assert intent.mode == "solo"

    def test_surface_is_cli_by_default(self) -> None:
        """Default ``surface`` is ``cli`` so the facade knows where the intent came from."""
        args = CliRunArgs(profile="/p.yaml", user_text="hi")
        intent = cli_args_to_intent(args)
        assert intent.surface == "cli"

    def test_cli_runs_have_no_prior_turns(self) -> None:
        """CLI runs always start fresh — ``prior_turns`` is empty."""
        args = CliRunArgs(profile="/p.yaml", user_text="hi")
        intent = cli_args_to_intent(args)
        assert intent.prior_turns == ()


# ── Optional field carry-through ─────────────────────────────────────


class TestOptionalFieldCarryThrough:
    def test_carries_session_id(self) -> None:
        """``args.session_id`` propagates to ``intent.session_id``."""
        args = CliRunArgs(profile="/p.yaml", user_text="hi", session_id="sess-cli-1")
        intent = cli_args_to_intent(args)
        assert intent.session_id == "sess-cli-1"

    def test_carries_assistant_id(self) -> None:
        """``args.assistant_id`` propagates to ``intent.assistant_id``."""
        args = CliRunArgs(profile="/p.yaml", user_text="hi", assistant_id="asst_cli")
        intent = cli_args_to_intent(args)
        assert intent.assistant_id == "asst_cli"

    def test_carries_device_id(self) -> None:
        """``args.device_id`` propagates to ``intent.device_id``."""
        args = CliRunArgs(profile="/p.yaml", user_text="hi", device_id="dev-cli")
        intent = cli_args_to_intent(args)
        assert intent.device_id == "dev-cli"

    def test_empty_attachment_ids_default(self) -> None:
        """Default ``attachment_ids`` is an empty tuple."""
        args = CliRunArgs(profile="/p.yaml", user_text="hi")
        intent = cli_args_to_intent(args)
        assert intent.attachment_ids == ()


# ── Options forwarding ───────────────────────────────────────────────


class TestOptionsForwarding:
    def test_options_dict_passed_through(self) -> None:
        """Mapping options are forwarded as a dict on the intent."""
        opts: Mapping[str, Any] = {"idempotency_key": "cli-1", "max_steps": 3}
        args = CliRunArgs(profile="/p.yaml", user_text="hi", options=opts)
        intent = cli_args_to_intent(args)
        assert dict(intent.options) == dict(opts)

    def test_options_none_becomes_empty_dict(self) -> None:
        """``args.options = None`` → empty dict on the intent (RunIntent requires dict-like)."""
        args = CliRunArgs(profile="/p.yaml", user_text="hi", options=None)
        intent = cli_args_to_intent(args)
        assert dict(intent.options) == {}
