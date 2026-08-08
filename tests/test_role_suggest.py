"""role_suggest 单元测试 —— 对齐 agency-orchestrator test/run.ts suggestFromPaths。"""

from __future__ import annotations

import unittest

from lca.layer4_app.role_suggest import suggest_from_paths


class TestSuggestFromPaths(unittest.TestCase):
    def test_substring_match_ranks_first(self) -> None:
        catalog = [
            "eng/eng-backend-architect",
            "eng/eng-frontend-dev",
            "design/design-ux-researcher",
        ]
        result = suggest_from_paths("eng/backend-architect", catalog)
        self.assertEqual(result[0], "eng/eng-backend-architect")

    def test_user_researcher_alias_maps_to_ux_researcher(self) -> None:
        catalog = [
            "design/design-ux-researcher",
            "product/product-manager",
        ]
        result = suggest_from_paths("user-researcher", catalog)
        self.assertEqual(result[0], "design/design-ux-researcher")

    def test_empty_catalog_returns_empty(self) -> None:
        self.assertEqual(suggest_from_paths("whatever/role", []), [])

    def test_gibberish_returns_empty(self) -> None:
        catalog = ["design/design-ux-researcher", "product/product-manager"]
        self.assertEqual(suggest_from_paths("zzz/qqqqwwwweeee-xxxxyyyy", catalog), [])

    def test_default_limit_is_three(self) -> None:
        catalog = [f"eng/eng-role-{i}" for i in range(10)]
        self.assertLessEqual(len(suggest_from_paths("eng/engineer", catalog)), 3)


if __name__ == "__main__":
    unittest.main()
