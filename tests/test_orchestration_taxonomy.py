"""ADR-0027: process↔family map and reserved industry slots."""

from __future__ import annotations

import pytest

from lca.contracts.enums import DecisionGateName, TeamProcess
from lca.contracts.orchestration_taxonomy import (
    RESERVED_PROCESS_SLOTS,
    OrchestrationFamily,
    SupervisorPlane,
    assert_process_family_complete,
    family_of,
)
from lca.contracts.role_team import TeamConfig


def test_process_family_map_is_complete() -> None:
    assert_process_family_complete()


@pytest.mark.parametrize(
    ("process", "family"),
    [
        (TeamProcess.HIERARCHICAL, OrchestrationFamily.SUPERVISOR),
        (TeamProcess.SEQUENTIAL, OrchestrationFamily.CHOREOGRAPHY),
        (TeamProcess.PARALLEL, OrchestrationFamily.CHOREOGRAPHY),
        (TeamProcess.DEBATE, OrchestrationFamily.CHOREOGRAPHY),
        (TeamProcess.HANDOFF, OrchestrationFamily.PEER),
        (TeamProcess.SWARM, OrchestrationFamily.PEER),
        (TeamProcess.GRAPH, OrchestrationFamily.GRAPH),
    ],
)
def test_family_of(process: TeamProcess, family: OrchestrationFamily) -> None:
    assert family_of(process) is family
    # TeamConfig holds process only; family is derived via taxonomy helper (ADR-0015)
    assert family_of(TeamConfig(process=process).process) is family


def test_team_config_defaults_align_industry_free_supervisor() -> None:
    cfg = TeamConfig(process=TeamProcess.HIERARCHICAL)
    assert cfg.decision_gate is DecisionGateName.NONE
    assert cfg.supervisor_plane is SupervisorPlane.CONSULTATION


def test_reserved_slots_do_not_collide_with_live_processes() -> None:
    live = {p.value for p in TeamProcess}
    assert RESERVED_PROCESS_SLOTS.isdisjoint(live)
