"""Regression test: ``step.tool_result.record`` payload surfaces failure_kind.

The Body executor's deterministic-failure stop policy
(``DefaultStopPolicy._deterministic_failure_stop``) reads
``observation.extra[FAILURE_KIND]`` to decide whether to short-circuit
the loop instead of letting the agent retry the same call until the
budget burns out. Until now the spine fact committed by
``record_step_tool_result`` did not surface that tag — observers and
post-hoc replays could not distinguish a deterministic read failure
from a transient retryable one.

This test pins the contract: when the caller passes ``failure_kind``,
it must appear in the spine payload; otherwise the field is absent
(paying zero overhead on the happy path).
"""

from __future__ import annotations

from lca.contracts.atoms.semantic.keys import FAILURE_KIND_EXECUTION
from lca.loop.commit.tool_journal import record_step_tool_result


def _capture_publish_ep_bound(monkeypatch) -> list[dict]:
    """Patch ``publish_ep_bound`` to capture the spine payload dict.

    Returns the captured list so individual tests can inspect the last
    appended entry. The patch is reset by ``monkeypatch`` after each test.
    """
    captured: list[dict] = []

    def _fake_publish(ep: str, payload: dict, **kwargs):
        captured.append({"ep": ep, "payload": payload})
        return None

    monkeypatch.setattr("lca.loop.commit.tool_journal.publish_ep_bound", _fake_publish)
    return captured


def test_failure_kind_surfaces_when_provided(monkeypatch) -> None:
    captured = _capture_publish_ep_bound(monkeypatch)
    record_step_tool_result(
        tool_name="readFile",
        invocation_id="toolu_test_001",
        outcome="failure",
        ok=False,
        error="not a file: /mnt/data/foo.md",
        failure_kind=FAILURE_KIND_EXECUTION,
    )
    assert len(captured) == 1
    payload = captured[0]["payload"]
    assert payload["outcome"] == "failure"
    assert payload["ok"] is False
    assert payload["failure_kind"] == FAILURE_KIND_EXECUTION
    assert payload["error"] == "not a file: /mnt/data/foo.md"


def test_failure_kind_absent_when_not_provided(monkeypatch) -> None:
    captured = _capture_publish_ep_bound(monkeypatch)
    record_step_tool_result(
        tool_name="listFiles",
        invocation_id="toolu_test_002",
        outcome="ok",
        ok=True,
    )
    assert len(captured) == 1
    payload = captured[0]["payload"]
    assert "failure_kind" not in payload, (
        "Happy-path records must not pay a failure_kind field; absence is "
        "the SSOT signal that no failure classification was attached."
    )


def test_failure_kind_accepts_transient_tag(monkeypatch) -> None:
    captured = _capture_publish_ep_bound(monkeypatch)
    record_step_tool_result(
        tool_name="runCommand",
        invocation_id="toolu_test_003",
        outcome="timeout",
        ok=False,
        failure_kind="transient",
    )
    payload = captured[0]["payload"]
    assert payload["failure_kind"] == "transient"
    assert payload["outcome"] == "timeout"


def test_failure_kind_none_is_treated_as_absent(monkeypatch) -> None:
    captured = _capture_publish_ep_bound(monkeypatch)
    record_step_tool_result(
        tool_name="readFile",
        invocation_id="toolu_test_004",
        outcome="failure",
        ok=False,
        failure_kind=None,
    )
    payload = captured[0]["payload"]
    assert "failure_kind" not in payload
