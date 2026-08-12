"""Patch: topic_route — Stabilize topicId resolution from pathname."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="topic_route",
    description="Stabilize topicId resolution from pathname",
    files=(
        "src/features/AgentSidebar/utils/agentPathname.ts",
        "src/routes/(main)/agent/features/Conversation/ChatHydration/useChatRouteSync.ts",
        "src/routes/(main)/agent/_layout/AgentIdSync.tsx",
    ),
    risk="medium",
    category="route",
    depends_on=(),
    why="LCA needs stable topicId from URL; LobeHub's default resolution is fragile",
    technical_detail=(
        "Add resolveAgentChatRouteTopicId() that prefers route params over pathname parsing. "
        "Update useChatRouteSync and AgentIdSync to use it."
    ),
    verify_file="src/features/AgentSidebar/utils/agentPathname.ts",
    verify_marker="resolveAgentChatRouteTopicId",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    changed = False

    rel_path = "src/features/AgentSidebar/utils/agentPathname.ts"
    text = ctx.read(rel_path)
    if "resolveAgentChatRouteTopicId" not in text:
        sub_routes = """/** Agent chat sub-routes — not topic ids (see desktopRouter `agent/:aid/...`). */
const AGENT_CHAT_SUB_ROUTES = new Set([
  'channel',
  'docs',
  'permission',
  'profile',
  'statistics',
  'stats',
  'task',
  'tasks',
  'topics',
]);

"""
        if "AGENT_CHAT_SUB_ROUTES" not in text:
            text = text.replace(
                "export interface AgentPathnameInfo {",
                sub_routes + "export interface AgentPathnameInfo {",
                1,
            )
        insert_fn = """
/**
 * Resolve the active topic id from an agent chat URL.
 * Falls back to pathname parsing when React Router params are briefly stale.
 */
export const resolveAgentChatRouteTopicId = (
  pathname: string,
  paramsTopicId?: string,
): string | undefined => {
  if (paramsTopicId) return paramsTopicId;

  const agentRoute = parseAgentPathname(pathname);
  if (!agentRoute) return undefined;

  const [firstSegment] = agentRoute.segmentsAfterAgent;
  if (!firstSegment || agentRoute.segmentsAfterAgent.length !== 1) return undefined;
  if (AGENT_CHAT_SUB_ROUTES.has(firstSegment)) return undefined;

  return firstSegment;
};

"""
        anchor = "export const buildPrefixedAgentRoutePath = ("
        if anchor not in text:
            raise SystemExit("[topic_route_path] anchor not found")
        text = text.replace(anchor, insert_fn + anchor, 1)
        ctx.write(rel_path, text)
        changed = True

    rel_sync = "src/routes/(main)/agent/features/Conversation/ChatHydration/useChatRouteSync.ts"
    text = ctx.read(rel_sync)
    if "resolveAgentChatRouteTopicId" not in text:
        text = text.replace(
            "import { useWorkspaceAwareNavigate } from '@/features/Workspace/useWorkspaceAwareNavigate';",
            "import { resolveAgentChatRouteTopicId } from '@/features/AgentSidebar/utils/agentPathname';\n"
            "import { useWorkspaceAwareNavigate } from '@/features/Workspace/useWorkspaceAwareNavigate';",
            1,
        )
        text = text.replace(
            "  const routeTopicId = params.topicId;",
            "  const routeTopicId = resolveAgentChatRouteTopicId(location.pathname, params.topicId);",
            1,
        )
        text = text.replace(
            "        const { aid, topicId } = paramsRef.current;\n\n        if (!aid || state === topicId) return;",
            "        const { aid, topicId: paramsTopicId } = paramsRef.current;\n"
            "        const topicId = resolveAgentChatRouteTopicId(\n"
            "          locationRef.current.pathname,\n"
            "          paramsTopicId,\n"
            "        );\n\n        if (!aid || state === topicId) return;",
            1,
        )
        ctx.write(rel_sync, text)
        changed = True

    rel_agent = "src/routes/(main)/agent/_layout/AgentIdSync.tsx"
    text = ctx.read(rel_agent)
    if "resolveAgentChatRouteTopicId" not in text:
        text = text.replace(
            "import { useResolvedAgentRouteId } from '@/features/AgentRoute/useResolvedAgentRouteId';",
            "import { useResolvedAgentRouteId } from '@/features/AgentRoute/useResolvedAgentRouteId';\n"
            "import { resolveAgentChatRouteTopicId } from '@/features/AgentSidebar/utils/agentPathname';",
            1,
        )
        text = text.replace(
            "    topicFromPath: params.topicId,",
            "    topicFromPath: resolveAgentChatRouteTopicId(location.pathname, params.topicId),",
            1,
        )
        ctx.write(rel_agent, text)
        changed = True

    return changed
