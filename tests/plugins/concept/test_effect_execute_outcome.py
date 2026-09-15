"""Regression: EffectReceipt outcome reflects Observation success.

Verifies that ``effect_execute._dispatch()`` derives ``EffectOutcome``
from the actual Observation returned by the gateway, not a hardcoded
default.
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.harness.act.effect_receipt import EffectOutcome
from lca.contracts.models.core.execution.decision import Observation
from lca.nodes.concept.effect.execute import _derive_outcome


class TestDeriveOutcome:
    def test_observation_success_returns_succeeded(self) -> None:
        obs = Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"stdout": "ok"},
            content_type=ContentType.STRUCTURED,
        )
        outcome, error_code, failure_kind = _derive_outcome(obs)
        assert outcome is EffectOutcome.SUCCEEDED
        assert error_code is None
        assert failure_kind is None

    def test_observation_failure_returns_failed(self) -> None:
        obs = Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            content_type=ContentType.TEXT,
            error="/bin/sh: cd: /files: No such file or directory",
        )
        outcome, error_code, failure_kind = _derive_outcome(obs)
        assert outcome is EffectOutcome.FAILED
        assert error_code is not None
        assert failure_kind is None

    def test_dict_with_observation_result_checks_success(self) -> None:
        obs = Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            content_type=ContentType.TEXT,
            error="tool failed",
        )
        outcome, error_code, failure_kind = _derive_outcome({"result": obs})
        assert outcome is EffectOutcome.FAILED
        assert error_code is not None
        assert failure_kind is None

    def test_dict_with_success_observation_returns_succeeded(self) -> None:
        obs = Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"stdout": "ok"},
            content_type=ContentType.STRUCTURED,
        )
        outcome, error_code, failure_kind = _derive_outcome({"result": obs})
        assert outcome is EffectOutcome.SUCCEEDED
        assert error_code is None
        assert failure_kind is None

    def test_non_observation_result_defaults_to_succeeded(self) -> None:
        for val in ("raw string", None, 42):
            outcome, error_code, failure_kind = _derive_outcome(val)
            assert outcome is EffectOutcome.SUCCEEDED
            assert error_code is None
            assert failure_kind is None

    def test_dict_without_observation_defaults_to_succeeded(self) -> None:
        outcome, error_code, failure_kind = _derive_outcome({"result": "text"})
        assert outcome is EffectOutcome.SUCCEEDED
        assert error_code is None
        assert failure_kind is None

    def test_observation_failure_with_failure_kind_tag(self) -> None:
        """Body executor's failure_kind tag must surface to the receipt.

        Regression for run_0d71855ae274 (cat /nonexistent returned
        ok=False without a failure_kind, so stop_policy never saw the
        deterministic-failure signal and burned all 8 max_visits).
        """
        from lca.contracts.atoms.semantic.keys import FAILURE_KIND

        obs = Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            content_type=ContentType.TEXT,
            error="cat: /nonexistent: No such file or directory",
            extra={FAILURE_KIND: "execution"},
        )
        outcome, _error_code, failure_kind = _derive_outcome(obs)
        assert outcome is EffectOutcome.FAILED
        assert failure_kind == "execution"
