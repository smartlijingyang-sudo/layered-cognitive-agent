"""Model-visible tool results show workspace-relative guest paths (ADR-0121).

The projection lives in the single live seam
``cognition.body.emit.observation_surface.observation_content``; receipts
and the journal keep guest absolute process paths.
"""

from __future__ import annotations

import json

from lca.cognition.body.emit.observation_surface import observation_content
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.external_content import (
    EXTERNAL_FENCE_BEGIN,
    ContentOrigin,
)


def _obs(payload: object, *, success: bool = True, error: str | None = None) -> Observation:
    return Observation(
        observation_id="obs_1",
        success=success,
        payload=payload,
        error=error,
        content_origin=ContentOrigin.INTERNAL,
    )


def test_listing_paths_become_workspace_relative() -> None:
    payload = {
        "success": True,
        "directoryPath": "/mnt/data",
        "files": [
            {"name": "outputs", "isDirectory": True, "path": "/mnt/data/outputs"},
            {"name": "a.xlsx", "isDirectory": False, "path": "/mnt/data/a.xlsx", "size": 3},
        ],
        "totalCount": 2,
    }
    shown = json.loads(observation_content(_obs(payload)))
    assert shown["directoryPath"] == "."
    assert shown["files"][0]["path"] == "outputs"
    assert shown["files"][1]["path"] == "a.xlsx"
    assert "/mnt/data" not in observation_content(_obs(payload))


def test_root_itself_collapses_to_dot() -> None:
    assert json.loads(observation_content(_obs({"path": "/mnt/data"})))["path"] == "."


def test_paths_outside_guest_root_stay_absolute() -> None:
    assert json.loads(observation_content(_obs({"path": "/var/data/chart.png"})))["path"] == (
        "/var/data/chart.png"
    )


def test_content_values_under_non_whitelisted_keys_are_not_rewritten() -> None:
    payload = {"content": "/mnt/data/notes.txt says keep this absolute"}
    assert json.loads(observation_content(_obs(payload)))["content"] == (
        "/mnt/data/notes.txt says keep this absolute"
    )


def test_string_payload_is_free_text_and_stays_untouched() -> None:
    assert observation_content(_obs("ls: /mnt/data/outputs")) == "ls: /mnt/data/outputs"


def test_external_origin_still_projects_paths_inside_the_fence() -> None:
    obs = Observation(
        observation_id="obs_2",
        success=True,
        payload={"path": "/mnt/data/a.xlsx"},
        content_origin=ContentOrigin.EXTERNAL,
    )
    text = observation_content(obs)
    assert text.startswith(EXTERNAL_FENCE_BEGIN)
    assert '"path": "a.xlsx"' in text


def test_error_text_is_not_projected() -> None:
    from lca.cognition.body.emit.observation_surface import observation_error
    from lca.infrastructure.session.projections.tool_result_message import tool_error_text

    obs = _obs(None, success=False, error="not a file: /mnt/data/x")
    assert observation_content(obs) == ""
    assert "/mnt/data/x" in tool_error_text(observation_error(obs))
