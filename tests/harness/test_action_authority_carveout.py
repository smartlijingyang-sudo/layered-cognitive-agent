from __future__ import annotations

import pytest

from lca.harness.declarative.action_authority import compile_action_authority


def test_empty_task_carveout_does_not_create_an_empty_forbidden_action() -> None:
    authority = compile_action_authority((), task_contract="!   ")

    assert "" not in authority.forbidden_actions
    assert authority.forbidden_actions == frozenset()


def test_unknown_task_carveout_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown action carve-out: invent_action"):
        compile_action_authority((), task_contract="!invent_action")
