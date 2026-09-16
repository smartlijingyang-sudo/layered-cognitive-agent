"""Pin the terminal spine EPs' catalog membership after the stop-decision retirement.

Plan `docs/plans/2026-09-14-stop-decision-retirement.md` PR-2 added two EPs to
the closed catalog:

- `terminal.commit` — emitted by the outer plan's terminal node via its
  declared `emit_on_exit`. Its payload is `{"state_id": ...}` only.
- `body.deterministic_fail` — reserved. No producer exists: the
  `DeterministicToolError` raise path was never built.

Neither maps the run outcome. `kernel.run.stop` is the fold's sole run-outcome
authority, so these EPs must not be able to move `terminal_outcome`.
"""

from __future__ import annotations

from lca_kernel.events.payloads.spine import SPINE_EVENT_CATEGORIES, SPINE_EXECUTION_POINTS


def test_terminal_commit_in_execution_points() -> None:
    assert "terminal.commit" in SPINE_EXECUTION_POINTS


def test_body_deterministic_fail_in_execution_points() -> None:
    assert "body.deterministic_fail" in SPINE_EXECUTION_POINTS


def test_terminal_commit_in_event_categories() -> None:
    assert "spine.terminal.commit" in SPINE_EVENT_CATEGORIES


def test_body_deterministic_fail_in_event_categories() -> None:
    assert "spine.body.deterministic_fail" in SPINE_EVENT_CATEGORIES


def test_terminal_commit_emission_does_not_move_the_folded_outcome() -> None:
    """`terminal.commit` carries no outcome, so it must not decide the run's.

    Its payload is `{"state_id": ...}` only, so any fold branch keyed on this
    EP has no outcome to read and would fall through to a default. Guarding
    the reachable case: the event is emitted in production, and re-adding a
    branch for it without giving it an outcome payload would stamp every
    successful run `failed`. `kernel.run.stop` is the authority. This drives
    the public fold over a real-shaped ledger rather than calling
    `_capture_outcome` with a category-prefixed EP, which the spine whitelist
    never admits and `_coerce` never produces.
    """
    from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree

    def _rec(seq: int, ep: str, payload: dict) -> dict:
        return {
            "event_id": f"run_t:{seq}",
            "category": f"spine.{ep}",
            "channel": "fact",
            "execution_point": ep,
            "payload": {"run_id": "run_t", "trace_id": "trace_t", **payload},
            "ts": f"2026-09-17T00:00:{seq:02d}.000000+00:00",
        }

    events = [
        _rec(1, "kernel.run.start", {}),
        _rec(2, "terminal.commit", {"state_id": "trace_t"}),
        _rec(3, "kernel.run.stop", {"outcome": "success"}),
    ]

    assert fold_step_tree(events, run_id="run_t").metadata.outcome == "completed"
