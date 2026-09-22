from lca.infrastructure.vocal.tool_filter import VocalToolFilter


def test_filter_removes_send_message_for_subagent():
    tool_filter = VocalToolFilter()
    all_tools = ["read_file", "run_command", "send_message", "web_search"]

    subagent_tools = tool_filter.filter_tools_for_runtime(
        all_tools, origin="subagent"
    )
    assert "send_message" not in subagent_tools
    assert "read_file" in subagent_tools
    assert len(subagent_tools) == 3


def test_filter_retains_send_message_for_coordinator():
    tool_filter = VocalToolFilter()
    all_tools = ["read_file", "run_command", "send_message", "web_search"]

    parent_tools = tool_filter.filter_tools_for_runtime(
        all_tools, origin="user"
    )
    assert "send_message" in parent_tools
    assert len(parent_tools) == 4
