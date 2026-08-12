"""Patch: topic_route_test — Add test for resolveAgentChatRouteTopicId."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="topic_route_test",
    description="Add test for resolveAgentChatRouteTopicId",
    files=("src/features/AgentSidebar/utils/agentPathname.test.ts",),
    risk="low",
    category="route",
    depends_on=("topic_route",),
    why="Test coverage for the new routing function added by topic_route patch",
    technical_detail="Add test cases for resolveAgentChatRouteTopicId with params, pathname, and edge cases.",
    verify_file="src/features/AgentSidebar/utils/agentPathname.test.ts",
    verify_marker="resolveAgentChatRouteTopicId",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    rel = "src/features/AgentSidebar/utils/agentPathname.test.ts"
    text = ctx.read(rel)
    if "resolveAgentChatRouteTopicId" in text:
        return False
    text = text.replace(
        "import { buildPrefixedAgentRoutePath, parseAgentPathname } from './agentPathname';",
        "import { buildPrefixedAgentRoutePath, parseAgentPathname, resolveAgentChatRouteTopicId } from './agentPathname';",
        1,
    )
    anchor = "  it('preserves a detected prefix only when workspace navigation cannot restore it', () => {"
    if anchor not in text:
        raise SystemExit("[topic_route_test] anchor not found")
    text = text.replace(
        anchor,
        "  it('resolveAgentChatRouteTopicId prefers params but falls back to pathname', () => {\n"
        "    expect(resolveAgentChatRouteTopicId('/agent/agt_1/tpc_abc', 'tpc_abc')).toBe('tpc_abc');\n"
        "    expect(resolveAgentChatRouteTopicId('/agent/agt_1/tpc_abc')).toBe('tpc_abc');\n"
        "    expect(resolveAgentChatRouteTopicId('/agent/agt_1/profile')).toBeUndefined();\n"
        "    expect(resolveAgentChatRouteTopicId('/agent/agt_1/tpc_abc/profile')).toBeUndefined();\n"
        "  });\n"
        "\n"
        "  " + anchor,
        1,
    )
    ctx.write(rel, text)
    return True
