#!/usr/bin/env python3
"""Apply LCA ↔ LobeHub integration patches to lobehub-ui/ (idempotent)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "lobehub-ui"
MARKER = "/* LCA: lca.events integration */"


def _read(rel: str) -> str:
    path = UI / rel
    if not path.is_file():
        raise SystemExit(f"missing {path} — run ./scripts/sync_lobehub_ui.sh first")
    return path.read_text()


def _write(rel: str, text: str) -> None:
    (UI / rel).write_text(text)


def _done(name: str) -> None:
    print(f"[patch-lca-integration] {name}")


def patch_openai_stream() -> None:
    rel = "packages/model-runtime/src/core/streams/openai/openai.ts"
    text = _read(rel)
    if "LCA: emit lca.events" in text:
        _done(f"{rel} already patched")
        return
    needle = "  try {\n    // maybe need another structure to add support for multiple choices"
    insert = """  /* LCA: emit lca.events before OpenAI delta handling */
  const lcaExt = (chunk as { lca?: { events?: unknown[] } }).lca;
  if (lcaExt?.events?.length) {
    const events = lcaExt.events as Record<string, unknown>[];
    return events.map(
      (event): StreamProtocolChunk => ({
        data: event,
        id: chunk.id,
        type: 'lca_tool_event',
      }),
    );
  }

  try {
    // maybe need another structure to add support for multiple choices"""
    if needle not in text:
        raise SystemExit("openai.ts anchor not found")
    _write(rel, text.replace(needle, insert, 1))
    _done(f"patched {rel}")


def patch_protocol() -> None:
    rel = "packages/model-runtime/src/core/streams/protocol.ts"
    text = _read(rel)
    if "'lca_tool_event'" in text:
        _done(f"{rel} already patched")
        return
    text = text.replace(
        "    | 'tool_calls'\n",
        "    | 'tool_calls'\n    /* LCA Mode A tool lifecycle via gateway lca.events */\n    | 'lca_tool_event'\n",
        1,
    )
    anchor = "          case 'tool_calls': {"
    insert = """          case 'lca_tool_event': {
            await callbacks.onLcaToolEvent?.(data);
            break;
          }

          case 'tool_calls': {"""
    if anchor not in text:
        raise SystemExit("protocol.ts tool_calls anchor not found")
    _write(rel, text.replace(anchor, insert, 1))
    _done(f"patched {rel}")


def patch_chat_callbacks() -> None:
    rel = "packages/model-runtime/src/types/chat.ts"
    text = _read(rel)
    if "onLcaToolEvent" in text:
        _done(f"{rel} already patched")
        return
    anchor = "  onToolsCalling?: (data: {"
    insert = """  /** LCA gateway ``lca.events`` (tool_started / tool_result / tool_state / run_error). */
  onLcaToolEvent?: (event: Record<string, unknown>) => Promise<void> | void;
  onToolsCalling?: (data: {"""
    if anchor not in text:
        raise SystemExit("chat.ts onToolsCalling anchor not found")
    _write(rel, text.replace(anchor, insert, 1))
    _done(f"patched {rel}")


def patch_fetch_sse() -> None:
    rel = "packages/fetch-sse/src/fetchSSE.ts"
    text = _read(rel)
    if "lca_tool_event" in text:
        _done(f"{rel} already patched")
        return
    # extend onMessageHandle union
    text = text.replace(
        "      | MessageStopChunk,\n  ) => void;",
        "      | MessageStopChunk\n      | { event: Record<string, unknown>; type: 'lca_tool_event' },\n  ) => void;",
        1,
    )
    anchor = "        case 'tool_calls': {"
    insert = """        case 'lca_tool_event': {
          options.onMessageHandle?.({ event: data, type: 'lca_tool_event' });
          break;
        }

        case 'tool_calls': {"""
    if anchor not in text:
        raise SystemExit("fetchSSE.ts tool_calls anchor not found")
    _write(rel, text.replace(anchor, insert, 1))
    _done(f"patched {rel}")


def patch_streaming_types() -> None:
    rel = "src/store/chat/agents/types/streaming.ts"
    text = _read(rel)
    if "LcaStreamToolEvent" in text:
        _done(f"{rel} already patched")
        return
    type_block = """
/** LCA Mode A SSE events (gateway/lobehub_bridge/lca_sse_extension.py). */
export type LcaStreamToolEvent =
  | {
      api_name: string;
      arguments: string;
      closed_loop?: boolean;
      identifier: string;
      lca_tool_name?: string;
      tool_call_id: string;
      type: 'tool_started';
      wire_name: string;
    }
  | {
      closed_loop?: boolean;
      content?: string;
      error?: string;
      state?: Record<string, unknown>;
      tool_call_id: string;
      type: 'tool_result';
    }
  | {
      snapshot_seq?: number;
      state: Record<string, unknown>;
      tool_call_id: string;
      type: 'tool_state';
    }
  | { closed_loop?: boolean; code?: string; message: string; type: 'run_error' };

"""
    text = text.replace(
        "export interface StreamingCallbacks {",
        type_block + "export interface StreamingCallbacks {",
        1,
    )
    text = text.replace(
        "  transformToolCalls: (toolCalls: MessageToolCall[]) => ChatToolPayload[];",
        "  /** LCA Mode A: server-side tool events for UI merge. */\n  onLcaToolEvent?: (event: LcaStreamToolEvent) => void;\n  transformToolCalls: (toolCalls: MessageToolCall[]) => ChatToolPayload[];",
        1,
    )
    text = text.replace(
        "  usage?: ModelUsage;\n}\n\n/**\n * Stream chunk types",
        "  usage?: ModelUsage;\n  /** LCA Mode A: tools executed inside LCA — skip client call_tool loop. */\n  lcaClosedLoop?: boolean;\n  lcaRunError?: string;\n}\n\n/**\n * Stream chunk types",
        1,
    )
    text = text.replace(
        "  | { type: 'stop' };",
        "  | { event: LcaStreamToolEvent; type: 'lca_tool_event' }\n  | { type: 'stop' };",
        1,
    )
    _write(rel, text)
    _done(f"patched {rel}")


def patch_streaming_handler() -> None:
    rel = "src/store/chat/agents/StreamingHandler.ts"
    text = _read(rel)
    if "lcaClosedLoop" in text:
        _done(f"{rel} already patched")
        return
    text = text.replace(
        "  type StreamingResult,\n} from './types/streaming';",
        "  type StreamingResult,\n  type LcaStreamToolEvent,\n} from './types/streaming';",
        1,
    )
    text = text.replace(
        "  private tools?: ChatToolPayload[];\n\n  // ========== Image upload state ==========",
        "  private tools?: ChatToolPayload[];\n  /** LCA Mode A: server-side tool loop — do not client-loop. */\n  private lcaClosedLoop = false;\n  private lcaRunError?: string;\n  private lcaToolsById = new Map<string, ChatToolPayload>();\n\n  // ========== Image upload state ==========",
        1,
    )
    text = text.replace(
        "      case 'tool_calls': {\n        this.handleToolCallsChunk(chunk);\n        break;\n      }",
        "      case 'lca_tool_event': {\n        this.handleLcaToolEvent(chunk.event);\n        break;\n      }\n      case 'tool_calls': {\n        this.handleToolCallsChunk(chunk);\n        break;\n      }",
        1,
    )
    handler_method = """
  private handleLcaToolEvent(event: LcaStreamToolEvent): void {
    if (event.type === 'run_error') {
      this.lcaRunError = event.message;
      if (event.closed_loop) this.lcaClosedLoop = true;
      return;
    }
    if ('closed_loop' in event && event.closed_loop) this.lcaClosedLoop = true;

    if (event.type === 'tool_started') {
      const wireName =
        event.wire_name || `${event.identifier}____${event.api_name}`;
      const toolCalls = [
        {
          function: { arguments: event.arguments || '{}', name: wireName },
          id: event.tool_call_id,
          type: 'function' as const,
        },
      ];
      for (const tool of this.callbacks.transformToolCalls(toolCalls)) {
        this.lcaToolsById.set(tool.id, tool);
      }
      this.tools = [...this.lcaToolsById.values()];
      this.callbacks.onToolCallsUpdate(this.tools);
      this.callbacks.toggleToolCallingStreaming(this.context.messageId, [true]);
      if (!this.lcaClosedLoop) this.isFunctionCall = true;
      this.endReasoningIfNeeded();
      return;
    }

    if (event.type === 'tool_result' || event.type === 'tool_state') {
      const existing = this.lcaToolsById.get(event.tool_call_id);
      if (!existing) return;
      const updated: ChatToolPayload = { ...existing };
      if (event.type === 'tool_result') {
        if (event.content) updated.result = event.content;
        if (event.error) updated.error = event.error;
        if (event.state) updated.state = { ...(updated.state ?? {}), ...event.state };
      } else {
        updated.state = { ...(updated.state ?? {}), ...event.state };
      }
      this.lcaToolsById.set(event.tool_call_id, updated);
      this.tools = [...this.lcaToolsById.values()];
      this.callbacks.onToolCallsUpdate(this.tools);
    }
  }

"""
    text = text.replace(
        "  private handleToolCallsChunk(chunk: {",
        handler_method + "  private handleToolCallsChunk(chunk: {",
        1,
    )
    text = text.replace(
        "      tools: this.tools,\n      traceId: this.msgTraceId,",
        "      lcaClosedLoop: this.lcaClosedLoop,\n      lcaRunError: this.lcaRunError,\n      tools: this.tools,\n      traceId: this.msgTraceId,",
        1,
    )
    _write(rel, text)
    _done(f"patched {rel}")


def patch_client_llm_transport() -> None:
    rel = "src/store/chat/agents/transports/ClientLLMTransport.ts"
    text = _read(rel)
    if "lcaClosedLoop" in text:
        _done(f"{rel} already patched")
        return
    text = text.replace(
        "        onToolCallsUpdate: (tools) => this.dispatchMessage(assistantMessageId, { tools }),",
        "        onLcaToolEvent: (event) => handler.handleChunk({ event, type: 'lca_tool_event' }),"
        "\n        onToolCallsUpdate: (tools) => this.dispatchMessage(assistantMessageId, { tools }),",
        1,
    )
    # run_error surfacing
    anchor = (
        "    if (streamError && !interrupted) return { error: streamError, ok: false, output };"
    )
    insert = """    if (streamError && !interrupted) return { error: streamError, ok: false, output };

    if (finalResult?.lcaRunError && !interrupted && !output.content.trim()) {
      return {
        error: new Error(finalResult.lcaRunError),
        ok: false,
        output,
      };
    }"""
    if anchor not in text:
        raise SystemExit("ClientLLMTransport streamError anchor not found")
    text = text.replace(anchor, insert, 1)
    text = text.replace(
        "      toolCalls: result.toolCalls ?? [],\n      toolsCalling: result.tools ?? [],",
        "      lcaClosedLoop: result.lcaClosedLoop,\n      toolCalls: result.toolCalls ?? [],\n      toolsCalling: result.tools ?? [],",
        1,
    )
    _write(rel, text)
    _done(f"patched {rel}")


def patch_llm_transport_type() -> None:
    rel = "packages/agent-runtime/src/transport/llm.ts"
    text = _read(rel)
    if "lcaClosedLoop" in text:
        _done(f"{rel} already patched")
        return
    text = text.replace(
        "  toolCalls: MessageToolCall[];\n  toolsCalling: ChatToolPayload[];",
        "  /** LCA Mode A: skip GeneralChatAgent client tool loop. */\n  lcaClosedLoop?: boolean;\n  toolCalls: MessageToolCall[];\n  toolsCalling: ChatToolPayload[];",
        1,
    )
    _write(rel, text)
    _done(f"patched {rel}")


def patch_call_llm_finalizer() -> None:
    rel = "packages/agent-runtime/src/executors/callLlmFinalizer.ts"
    text = _read(rel)
    if "output.lcaClosedLoop" in text:
        _done(f"{rel} already patched")
        return
    repl = "hasToolsCalling: !output.lcaClosedLoop && output.toolsCalling.length > 0,"
    text = text.replace(
        "hasToolsCalling: output.toolsCalling.length > 0,",
        repl,
    )
    if repl not in text:
        raise SystemExit("callLlmFinalizer hasToolsCalling anchor not found")
    _write(rel, text)
    _done(f"patched {rel}")


LOCAL_DEV_NO_AUTH_TS = """\
/** LCA local stack: skip Better Auth session polling (no login, no get-session). */
export const isLocalDevNoAuth = (): boolean => {
  const flag = process.env.NEXT_PUBLIC_ENABLE_MOCK_DEV_USER;
  return flag === '1' || flag === 'true';
};

export const getLocalDevUserId = (): string =>
  process.env.NEXT_PUBLIC_MOCK_DEV_USER_ID ||
  process.env.MOCK_DEV_USER_ID ||
  'local-dev-user';
"""

LOCAL_DEV_USER_UPDATER_TSX = """\
'use client';

import { memo, useLayoutEffect } from 'react';

import { getLocalDevUserId } from '@/layout/AuthProvider/localDevNoAuth';
import { useUserStore } from '@/store/user';
import { type LobeUser } from '@/types/user';

/**
 * Static local user — replaces Better Auth `useSession()` polling.
 * Server APIs already trust `ENABLE_MOCK_DEV_USER` (see trpc lambda context).
 */
const LocalDevUserUpdater = memo(() => {
  useLayoutEffect(() => {
    const userId = getLocalDevUserId();
    const user: LobeUser = {
      avatar: '',
      email: 'dev@localhost',
      fullName: 'Local Dev',
      id: userId,
      username: 'local',
    };

    useUserStore.setState({
      isLoaded: true,
      isSignedIn: true,
      user,
    });
  }, []);

  return null;
});

LocalDevUserUpdater.displayName = 'LocalDevUserUpdater';

export default LocalDevUserUpdater;
"""

LOCAL_DEV_AUTH_INDEX_TSX = """\
import { type PropsWithChildren } from 'react';

import LocalDevUserUpdater from './LocalDevUserUpdater';

/** LCA: no login UI, no `/api/auth/get-session` polling. */
const LocalDevAuth = ({ children }: PropsWithChildren) => {
  return (
    <>
      {children}
      <LocalDevUserUpdater />
    </>
  );
};

export default LocalDevAuth;
"""


def patch_middleware_mock_dev_user() -> None:
    rel = "src/libs/next/proxy/define-config.ts"
    text = _read(rel)
    if "ENABLE_MOCK_DEV_USER: skipping session gate" in text:
        _done(f"{rel} middleware mock user already patched")
        return

    anchor = """    // Skip session lookup for public routes to reduce latency
    if (!isProtected) return response;

    // Get full session with user data (Next.js 15.2.0+ feature)"""
    insert = """    // Skip session lookup for public routes to reduce latency
    if (!isProtected) return response;

    // LCA local stack: skip Better Auth session gate (LocalDevAuth + API mock user).
    const mockDevFlag = process.env.ENABLE_MOCK_DEV_USER;
    if (mockDevFlag === '1' || mockDevFlag === 'true') {
      logBetterAuth('ENABLE_MOCK_DEV_USER: skipping session gate');
      return response;
    }

    // Get full session with user data (Next.js 15.2.0+ feature)"""
    if anchor not in text:
        raise SystemExit(f"{rel} middleware session anchor not found")
    _write(rel, text.replace(anchor, insert, 1))
    _done(f"patched {rel} middleware mock user bypass")


def patch_local_dev_no_auth() -> None:
    rel_auth = "src/layout/AuthProvider/localDevNoAuth.ts"
    rel_updater = "src/layout/AuthProvider/LocalDevAuth/LocalDevUserUpdater.tsx"
    rel_index = "src/layout/AuthProvider/LocalDevAuth/index.tsx"
    rel_vite = "src/layout/AuthProvider/index.vite.tsx"

    _write(rel_auth, LOCAL_DEV_NO_AUTH_TS)
    _write(rel_updater, LOCAL_DEV_USER_UPDATER_TSX)
    _write(rel_index, LOCAL_DEV_AUTH_INDEX_TSX)
    _done(f"wrote {rel_auth}, LocalDevAuth/")

    text = _read(rel_vite)
    if "LocalDevAuth" in text and "isLocalDevNoAuth" in text:
        _done(f"{rel_vite} already patched")
        return

    old = """import BetterAuth from './BetterAuth';
import Desktop from './Desktop';

const AuthProvider = ({ children }: PropsWithChildren) => {
  if (isDesktop) {
    return <Desktop>{children}</Desktop>;
  }

  // In SPA/Vite mode, always use BetterAuth.
  // If auth is not configured on the server, useSession() will return no session
  // and the user will be treated as not signed in — same effect as NoAuth.
  return <BetterAuth>{children}</BetterAuth>;
};"""
    new = """import BetterAuth from './BetterAuth';
import Desktop from './Desktop';
import LocalDevAuth from './LocalDevAuth';
import { isLocalDevNoAuth } from './localDevNoAuth';

const AuthProvider = ({ children }: PropsWithChildren) => {
  if (isDesktop) {
    return <Desktop>{children}</Desktop>;
  }

  // LCA local stack: static dev user, no Better Auth session polling.
  if (isLocalDevNoAuth()) {
    return <LocalDevAuth>{children}</LocalDevAuth>;
  }

  return <BetterAuth>{children}</BetterAuth>;
};"""
    if old not in text:
        if "LocalDevAuth" in text:
            _done(f"{rel_vite} already patched (non-default template)")
            return
        raise SystemExit(f"{rel_vite} AuthProvider anchor not found")
    _write(rel_vite, text.replace(old, new, 1))
    _done(f"patched {rel_vite}")


def patch_topic_route_sync() -> None:
    rel_path = "src/features/AgentSidebar/utils/agentPathname.ts"
    text = _read(rel_path)
    if "resolveAgentChatRouteTopicId" in text:
        _done(f"{rel_path} already patched")
    else:
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
            raise SystemExit(f"{rel_path} buildPrefixedAgentRoutePath anchor not found")
        _write(rel_path, text.replace(anchor, insert_fn + anchor, 1))
        _done(f"patched {rel_path}")

    rel_sync = "src/routes/(main)/agent/features/Conversation/ChatHydration/useChatRouteSync.ts"
    text = _read(rel_sync)
    if "resolveAgentChatRouteTopicId" in text:
        _done(f"{rel_sync} already patched")
    else:
        if "resolveAgentChatRouteTopicId" not in _read(rel_path):
            raise SystemExit("resolveAgentChatRouteTopicId missing — patch agentPathname first")
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
        _write(rel_sync, text)
        _done(f"patched {rel_sync}")

    rel_agent = "src/routes/(main)/agent/_layout/AgentIdSync.tsx"
    text = _read(rel_agent)
    if "resolveAgentChatRouteTopicId" in text:
        _done(f"{rel_agent} already patched")
    else:
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
        _write(rel_agent, text)
        _done(f"patched {rel_agent}")


def patch_local_dev_market_fork() -> None:
    """Skip Market OIDC on HTTP local dev — fork community agents into local DB only."""
    patches = [
        (
            "src/routes/(main)/community/(detail)/agent/features/Sidebar/ActionButton/ForkAndChat.tsx",
            "isLocalDevNoAuth",
            [
                (
                    "import { useMarketAuth } from '@/layout/AuthProvider/MarketAuth';",
                    "import { useMarketAuth } from '@/layout/AuthProvider/MarketAuth';\n"
                    "import { isLocalDevNoAuth } from '@/layout/AuthProvider/localDevNoAuth';",
                ),
                (
                    "    if (!canCreate || isLoading) return;\n"
                    "    // Check if user is authenticated\n"
                    "    if (!isAuthenticated) {",
                    "    if (!canCreate || isLoading) return;\n"
                    "    // LCA local dev: HTTP lacks secure context for Market OIDC PKCE — fork locally.\n"
                    "    const localDevFork = isLocalDevNoAuth();\n"
                    "    // Check if user is authenticated\n"
                    "    if (!localDevFork && !isAuthenticated) {",
                ),
            ],
            "localDevFork forkResult",
        ),
        (
            "src/routes/(main)/community/(detail)/group_agent/features/Sidebar/ActionButton/ForkGroupAndChat.tsx",
            "isLocalDevNoAuth",
            [
                (
                    "import { useMarketAuth } from '@/layout/AuthProvider/MarketAuth';",
                    "import { useMarketAuth } from '@/layout/AuthProvider/MarketAuth';\n"
                    "import { isLocalDevNoAuth } from '@/layout/AuthProvider/localDevNoAuth';",
                ),
                (
                    "    if (!canCreate || isLoading) return;\n"
                    "    // Check if user is authenticated\n"
                    "    if (!isAuthenticated) {",
                    "    if (!canCreate || isLoading) return;\n"
                    "    // LCA local dev: HTTP lacks secure context for Market OIDC PKCE — fork locally.\n"
                    "    const localDevFork = isLocalDevNoAuth();\n"
                    "    // Check if user is authenticated\n"
                    "    if (!localDevFork && !isAuthenticated) {",
                ),
            ],
            "localDevFork forkResult",
        ),
    ]

    agent_rel = patches[0][0]
    agent_text = _read(agent_rel)
    if (
        "localDevFork forkResult" in agent_text
        or "const localDevFork = isLocalDevNoAuth()" in agent_text
    ):
        if "let forkResult: { agent:" in agent_text:
            _done(f"{agent_rel} already patched")
        else:
            raise SystemExit(f"{agent_rel} partially patched — manual fix needed")
    else:
        text = agent_text
        for old, new in patches[0][2]:
            if old not in text:
                raise SystemExit(f"{agent_rel} anchor not found")
            text = text.replace(old, new, 1)
        old_fork = """      let actAs: number | undefined;
      if (activeWorkspaceId) {
        const { marketAccountId } = await lambdaClient.workspace.ensureMarketOrganization.mutate({
          autoProvision: true,
        });
        actAs = marketAccountId;
      }

      // Step 2: Fork the agent via Market API (single-item batch)
      const [forkOutcome] = await marketApiService.forkAgent([
        {
          actAs,
          identifier: newIdentifier,
          name: title,
          sourceIdentifier: identifier!,
          status: 'published',
          visibility: 'public',
        },
      ]);

      if (!forkOutcome.success) {
        throw new Error(forkOutcome.error?.message || 'Forking failed');
      }

      const forkResult = forkOutcome.data;"""
        new_fork = """      let forkResult: { agent: { identifier: string; name: string } };
      if (localDevFork) {
        forkResult = { agent: { identifier: newIdentifier, name: title! } };
      } else {
        let actAs: number | undefined;
        if (activeWorkspaceId) {
          const { marketAccountId } = await lambdaClient.workspace.ensureMarketOrganization.mutate({
            autoProvision: true,
          });
          actAs = marketAccountId;
        }

        // Step 2: Fork the agent via Market API (single-item batch)
        const [forkOutcome] = await marketApiService.forkAgent([
          {
            actAs,
            identifier: newIdentifier,
            name: title,
            sourceIdentifier: identifier!,
            status: 'published',
            visibility: 'public',
          },
        ]);

        if (!forkOutcome.success) {
          throw new Error(forkOutcome.error?.message || 'Forking failed');
        }

        forkResult = forkOutcome.data;
      }"""
        if old_fork not in text:
            raise SystemExit(f"{agent_rel} fork block anchor not found")
        _write(agent_rel, text.replace(old_fork, new_fork, 1))
        _done(f"patched {agent_rel}")

    group_rel = patches[1][0]
    group_text = _read(group_rel)
    if (
        "const localDevFork = isLocalDevNoAuth()" in group_text
        and "let forkResult: { group:" in group_text
    ):
        _done(f"{group_rel} already patched")
    elif "const localDevFork = isLocalDevNoAuth()" not in group_text:
        text = group_text
        for old, new in patches[1][2]:
            if old not in text:
                raise SystemExit(f"{group_rel} anchor not found")
            text = text.replace(old, new, 1)
        old_fork = """      let actAs: number | undefined;
      if (activeWorkspaceId) {
        const { marketAccountId } = await lambdaClient.workspace.ensureMarketOrganization.mutate({
          autoProvision: true,
        });
        actAs = marketAccountId;
      }

      // Step 2: Fork the group via Market API
      const forkResult = await marketApiService.forkAgentGroup(identifier!, {
        actAs,
        identifier: newIdentifier,
        name: title,
        status: 'published',
        visibility: 'public',
      });"""
        new_fork = """      let forkResult: { group: { identifier: string } };
      if (localDevFork) {
        forkResult = { group: { identifier: newIdentifier } };
      } else {
        let actAs: number | undefined;
        if (activeWorkspaceId) {
          const { marketAccountId } = await lambdaClient.workspace.ensureMarketOrganization.mutate({
            autoProvision: true,
          });
          actAs = marketAccountId;
        }

        // Step 2: Fork the group via Market API
        forkResult = await marketApiService.forkAgentGroup(identifier!, {
          actAs,
          identifier: newIdentifier,
          name: title,
          status: 'published',
          visibility: 'public',
        });
      }"""
        if old_fork not in text:
            raise SystemExit(f"{group_rel} fork block anchor not found")
        _write(group_rel, text.replace(old_fork, new_fork, 1))
        _done(f"patched {group_rel}")


def main() -> None:
    if not UI.is_dir():
        print("[patch-lca-integration] skip: lobehub-ui/ missing", file=sys.stderr)
        sys.exit(0)
    patch_openai_stream()
    patch_protocol()
    patch_chat_callbacks()
    patch_fetch_sse()
    patch_streaming_types()
    patch_streaming_handler()
    patch_client_llm_transport()
    patch_llm_transport_type()
    patch_call_llm_finalizer()
    patch_local_dev_no_auth()
    patch_middleware_mock_dev_user()
    patch_local_dev_market_fork()
    patch_topic_route_sync()
    stamp = UI / ".lca-integration-patched"
    stamp.write_text(MARKER + "\n")
    _done("complete")


if __name__ == "__main__":
    main()
