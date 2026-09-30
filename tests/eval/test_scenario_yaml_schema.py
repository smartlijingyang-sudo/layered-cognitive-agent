"""验证商用级旗舰多轮对话评测 YAML 剧本契约与结构合规性。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_YAML_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "dialogue_scenarios"
    / "commercial_flagship_eval.yaml"
)

EXPECTED_QUADRANTS = {
    "muse_memory",
    "grok_wit",
    "grok_companion",
    "hermes_tools",
    "hermes_delegation",
    "hermes_evolution",
    "muse_defense",
    "commercial_dreaming",
}


def test_yaml_file_exists_and_contains_16_scenarios() -> None:
    assert _YAML_PATH.exists(), f"YAML 剧本库文件不存在: {_YAML_PATH}"
    with open(_YAML_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict), "YAML 根结构必须为字典"
    assert "scenarios" in data, "YAML 顶层必须包含 scenarios 列表"
    scenarios = data["scenarios"]
    assert isinstance(scenarios, list), "scenarios 必须为列表"
    assert len(scenarios) == 16, f"必须定义 16 套多轮对话场景，实得 {len(scenarios)}"

    quadrants = set()
    scenario_ids = set()

    for sc in scenarios:
        assert "id" in sc and "title" in sc and "quadrant" in sc and "turns" in sc
        sc_id = sc["id"]
        assert sc_id not in scenario_ids, f"场景 ID 重复: {sc_id}"
        scenario_ids.add(sc_id)

        quadrant = sc["quadrant"]
        assert quadrant in EXPECTED_QUADRANTS, f"未知能力象限: {quadrant}"
        quadrants.add(quadrant)

        turns = sc["turns"]
        assert isinstance(turns, list), f"场景 {sc_id} 的 turns 必须为列表"
        assert len(turns) >= 3, f"场景 {sc_id} 必须至少包含 3 轮对话，实得 {len(turns)}"

        prev_turn_num = 0
        for turn in turns:
            assert "turn" in turn, f"场景 {sc_id} 某轮缺失 turn 字段"
            turn_num = turn["turn"]
            assert turn_num == prev_turn_num + 1, (
                f"场景 {sc_id} 轮次编号不连续: 期望 {prev_turn_num + 1}, 实得 {turn_num}"
            )
            prev_turn_num = turn_num

            assert "user" in turn and turn["user"].strip(), (
                f"场景 {sc_id} 轮次 {turn_num} user 提问不能为空"
            )
            assert "expected_behavior" in turn and turn["expected_behavior"].strip(), (
                f"场景 {sc_id} 轮次 {turn_num} expected_behavior 不能为空"
            )

    assert quadrants == EXPECTED_QUADRANTS, (
        f"必须完整覆盖 8 大象限: {EXPECTED_QUADRANTS - quadrants}"
    )


def test_each_quadrant_has_exactly_two_scenarios() -> None:
    if not _YAML_PATH.exists():
        pytest.fail(f"YAML 剧本库文件不存在: {_YAML_PATH}")
    with open(_YAML_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    quadrant_counts: dict[str, int] = {}
    for sc in data.get("scenarios", []):
        q = sc.get("quadrant")
        quadrant_counts[q] = quadrant_counts.get(q, 0) + 1

    for q in EXPECTED_QUADRANTS:
        assert quadrant_counts.get(q) == 2, (
            f"象限 {q} 必须恰好包含 2 个场景，实得 {quadrant_counts.get(q)}"
        )
