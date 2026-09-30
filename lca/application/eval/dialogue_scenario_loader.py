"""多轮对话场景 YAML 剧本解析加载器。"""

from __future__ import annotations

from pathlib import Path

import yaml

from lca.application.eval.dialogue_scenario_models import (
    CommercialEvalSuite,
    DialogueScenario,
)

_DEFAULT_YAML_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "dialogue_scenarios"
    / "commercial_flagship_eval.yaml"
)


def parse_dialogue_scenarios_from_yaml(yaml_content: str) -> CommercialEvalSuite:
    """从 YAML 字符串解析为强类型 CommercialEvalSuite。"""
    raw_data = yaml.safe_load(yaml_content)
    if not isinstance(raw_data, dict):
        raise ValueError("YAML 根节点必须为映射字典")
    return CommercialEvalSuite.model_validate(raw_data)


def load_commercial_scenarios(
    path: Path | str | None = None,
) -> list[DialogueScenario]:
    """从磁盘加载商用多轮对话评测场景列表。"""
    resolved_path = Path(path) if path is not None else _DEFAULT_YAML_PATH
    if not resolved_path.exists():
        raise FileNotFoundError(f"评测剧本文件未找到: {resolved_path}")

    with open(resolved_path, encoding="utf-8") as f:
        content = f.read()

    suite = parse_dialogue_scenarios_from_yaml(content)
    return list(suite.scenarios)
