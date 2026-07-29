"""GroupChat 已降级：mesh 图构建明确失败。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lca.layer3_agent.group_chat import build_group_chat_graph


class TestGroupChatDemoted(unittest.TestCase):
    def test_mesh_builder_raises(self) -> None:
        with self.assertRaises(NotImplementedError):
            build_group_chat_graph(["a", "b", "c"])

    def test_empty_roles_raises(self) -> None:
        with self.assertRaises(NotImplementedError):
            build_group_chat_graph([])


if __name__ == "__main__":
    unittest.main()
