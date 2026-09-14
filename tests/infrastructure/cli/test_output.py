"""Tests for the shared OutputMode dispatcher."""

from __future__ import annotations

import json

from lca.infrastructure.cli.commands._shared.output import OutputMode, emit


def _payload() -> dict[str, object]:
    return {"run_id": "run_x", "nodes": 3}


def _human(p: dict[str, object]) -> str:
    return f"run={p['run_id']} nodes={p['nodes']}"


def test_emit_json_writes_indented_dict(capsys: object) -> None:
    emit(OutputMode.JSON, _payload(), human_renderer=_human)
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    parsed = json.loads(out)
    assert parsed["run_id"] == "run_x"
    assert parsed["nodes"] == 3


def test_emit_human_writes_renderer_output(capsys: object) -> None:
    emit(OutputMode.HUMAN, _payload(), human_renderer=_human)
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert out == "run=run_x nodes=3\n"


def test_output_mode_str_values_match_flag() -> None:
    assert OutputMode.JSON.value == "json"
    assert OutputMode.HUMAN.value == "human"
