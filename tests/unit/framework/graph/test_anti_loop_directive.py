"""Anti-loop directive in tool-usage prompt section.

Regression for runs run_76709886ad14 / run_e0163b5aece8: the LLM
sees only its own apology in the model-visible surface, has no
signal to stop repeating rejected / empty tool calls, and the
graph loops until max_visits is exceeded.
"""

from lca.plugins.prompts.sections import _REACT_TOOL_USAGE_TEXT


def test_tool_usage_guidelines_contain_anti_loop_directive() -> None:
    assert "rejected" in _REACT_TOOL_USAGE_TEXT
    assert "do not repeat" in _REACT_TOOL_USAGE_TEXT
