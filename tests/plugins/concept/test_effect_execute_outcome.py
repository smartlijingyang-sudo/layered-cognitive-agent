"""Regression: EffectReceipt outcome reflects Observation success.

Verifies that ``effect_execute._dispatch()`` derives ``EffectOutcome``
from the actual Observation returned by the gateway, not a hardcoded
default.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.harness.act.effect_receipt import EffectOutcome
from lca.contracts.models.core.execution.decision import Observation
from lca.plugins.concept.effect_execute.execute import _derive_outcome


class TestDeriveOutcome:
    def test_observation_success_returns_succeeded(self) -> None:
        obs = Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"stdout": "ok"},
            content_type=ContentType.STRUCTURED,
        )
        outcome, error_code = _derive_outcome(obs)
        assert outcome is EffectOutcome.SUCCEEDED
        assert error_code is None

    def test_observation_failure_returns_failed(self) -> None:
        obs = Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            content_type=ContentType.TEXT,
            error="/bin/sh: cd: /files: No such file or directory",
        )
        outcome, error_code = _derive_outcome(obs)
        assert outcome is EffectOutcome.FAILED
        assert error_code is not None

    def test_dict_with_observation_result_checks_success(self) -> None:
        obs = Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            content_type=ContentType.TEXT,
            error="tool failed",
        )
        outcome, error_code = _derive_outcome({"result": obs})
        assert outcome is EffectOutcome.FAILED
        assert error_code is not None

    def test_dict_with_success_observation_returns_succeeded(self) -> None:
        obs = Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"stdout": "ok"},
            content_type=ContentType.STRUCTURED,
        )
        outcome, error_code = _derive_outcome({"result": obs})
        assert outcome is EffectOutcome.SUCCEEDED
        assert error_code is None

    def test_non_observation_result_defaults_to_succeeded(self) -> None:
        for val in ("raw string", None, 42):
            outcome, error_code = _derive_outcome(val)
            assert outcome is EffectOutcome.SUCCEEDED
            assert error_code is None

    def test_dict_without_observation_defaults_to_succeeded(self) -> None:
        outcome, error_code = _derive_outcome({"result": "text"})
        assert outcome is EffectOutcome.SUCCEEDED
        assert error_code is None
