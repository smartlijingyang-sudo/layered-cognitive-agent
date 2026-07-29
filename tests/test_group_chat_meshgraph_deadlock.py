"""GroupChat demoted."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lca.layer3_agent.group_chat import build_group_chat_graph


class TestGroupChatDemoted(unittest.TestCase):
    def test_raises(self):
        with self.assertRaises(NotImplementedError):
            build_group_chat_graph(["a", "b"])


if __name__ == "__main__":
    unittest.main()
