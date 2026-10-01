"""COMMON FieldSpec 表回归测试：同名字典键不得静默覆盖。

历史事故：COMMON 曾同时存在 source="argument" 与 source="observation" 的
"page_size" 条目，后者静默覆盖前者，导致 search_skill 的 argument schema
渲染出 observation field。裁决：argument 版保留 "page_size"，
observation 版改名为 "result_page_size"。
"""

import ast
import pathlib
import unittest
from collections import Counter

from lca.infrastructure.tools.contract import COMMON

_SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "lca"
    / "infrastructure"
    / "tools"
    / "contract"
    / "schema"
    / "schema.py"
)


def _common_dict_keys() -> list[str]:
    tree = ast.parse(_SCHEMA_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        target = None
        value = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
            for t in targets:
                if isinstance(t, ast.Name) and t.id == "COMMON":
                    target = t
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "COMMON":
                target, value = node.target, node.value
        if target is not None and isinstance(value, ast.Dict):
            keys = []
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.append(k.value)
            return keys
    raise AssertionError("COMMON dict literal not found in schema.py")


class TestCommonFieldSpecNoShadow(unittest.TestCase):
    def test_no_duplicate_keys_in_literal(self) -> None:
        """字典字面量层面无重复键 —— 静默覆盖无法再次发生。"""
        keys = _common_dict_keys()
        dupes = sorted(k for k, n in Counter(keys).items() if n > 1)
        self.assertEqual(dupes, [], f"shadowed COMMON keys: {dupes}")

    def test_page_size_is_argument(self) -> None:
        self.assertEqual(COMMON["page_size"].source, "argument")
        self.assertEqual(COMMON["page_size"].wire_key, "pageSize")

    def test_result_page_size_is_observation(self) -> None:
        spec = COMMON["result_page_size"]
        self.assertEqual(spec.source, "observation")
        self.assertEqual(spec.python_key, "page_size")
        self.assertEqual(spec.wire_key, "pageSize")


if __name__ == "__main__":
    unittest.main()
