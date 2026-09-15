"""EffectReceipt.failure_kind crosses the Body↔Cognition seam intact.

Regression for run_0d71855ae274: ``_build_observation`` previously
constructed ``Observation(extra={})`` regardless of the receipt's
failure classification. ``act.observe`` now reads the tag inside
``Observation.extra[FAILURE_KIND]`` to set ``should_terminate=True``;
without it, the 8 max_visits burn out on the same failed tool call.
"""

from __future__ import annotations

from lca.contracts.atoms.semantic.keys import FAILURE_KIND
from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.models.core.execution.decision import Observation
from lca.nodes.concept.reflection_critique.observation_build import (
    _build_observation,
)


def _receipt(
    *,
    outcome: EffectOutcome,
    error_code: str | None = None,
    failure_kind: str | None = None,
) -> EffectReceipt:
    return EffectReceipt(
        invocation_id="iv1",
        outcome=outcome,
        idempotency_key="idem1",
        provider="body.run_command",
        error_code=error_code,
        failure_kind=failure_kind,
    )


def test_failed_receipt_projects_failure_kind_to_observation_extra() -> None:
    obs = _build_observation(
        _receipt(
            outcome=EffectOutcome.FAILED,
            error_code="cat: /no/such/file: No such file or directory",
            failure_kind="execution",
        )
    )
    assert isinstance(obs, Observation)
    assert obs.success is False
    assert obs.error == "cat: /no/such/file: No such file or directory"
    assert obs.extra.get(FAILURE_KIND) == "execution"


def test_succeeded_receipt_produces_empty_extra() -> None:
    """Success path must not carry failure_kind forward.

    The cognition seam treats ``Observation.extra[FAILURE_KIND]`` as a
    failure signal; success should leave the extra map alone so a
    downstream ``is_producer_tool`` / ``_has_user_visible_delivery``
    reader doesn't see a stale classification.
    """
    obs = _build_observation(_receipt(outcome=EffectOutcome.SUCCEEDED))
    assert obs.success is True
    assert obs.extra == {}


def test_failed_receipt_without_failure_kind_omits_tag() -> None:
    """A failed receipt without a tag must still produce a non-execution extra.

    Old observations pre-dating the classifier have no tag; stop-policy
    now treats ``success=False`` + ``error`` as deterministic failure,
    so we don't lose any safety here, but the typed projection must
    not invent a tag out of thin air.
    """
    obs = _build_observation(
        _receipt(
            outcome=EffectOutcome.FAILED,
            error_code="some error",
        )
    )
    assert obs.success is False
    assert FAILURE_KIND not in obs.extra
