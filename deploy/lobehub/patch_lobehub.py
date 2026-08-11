#!/usr/bin/env python3
"""Unified LCA ↔ LobeHub patch engine.

Single entry point for all LobeHub source customizations:
  apply  — idempotent patch application (default)
  verify — dry-run anchor/marker check for upgrade compatibility
  list   — print patch manifest

Usage:
  python3 deploy/lobehub/patch_lobehub.py              # apply all
  python3 deploy/lobehub/patch_lobehub.py verify       # check anchors
  python3 deploy/lobehub/patch_lobehub.py list         # show manifest
  python3 deploy/lobehub/patch_lobehub.py apply openai_stream protocol  # specific
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "lobehub-ui"
STAMP_FILE = UI / ".lca-patched"

# ── Types ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PatchMeta:
    name: str
    description: str
    files: tuple[str, ...]
    risk: str
    category: str


@dataclass
class PatchResult:
    name: str
    status: str  # applied | skipped | ok | broken | missing_file
    detail: str = ""


# ── Utilities ──────────────────────────────────────────────────────────


def _read(rel: str) -> str:
    path = UI / rel
    if not path.is_file():
        raise SystemExit(f"missing {path} — run ./scripts/sync_lobehub_ui.sh first")
    return path.read_text()


def _write(rel: str, text: str) -> None:
    (UI / rel).write_text(text)


def _replace_once(text: str, anchor: str, replacement: str, *, label: str) -> str:
    if anchor not in text:
        raise SystemExit(f"[{label}] anchor not found")
    return text.replace(anchor, replacement, 1)


def _log(tag: str, name: str, msg: str = "") -> None:
    suffix = f" — {msg}" if msg else ""
    print(f"[patch] {tag:7s} {name}{suffix}")


# ── New-file content (dev auth) ───────────────────────────────────────

_LOCAL_DEV_NO_AUTH_TS = """\
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

_LOCAL_DEV_USER_UPDATER_TSX = """\
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

_LOCAL_DEV_AUTH_INDEX_TSX = """\
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


# =======================================================================
#  PATCH FUNCTIONS
#  Each: () -> bool  (True=applied, False=already done)
#  Raise SystemExit on anchor mismatch.
# =======================================================================

# ── 1. Streaming Protocol ─────────────────────────────────────────────


def p_openai_stream() -> bool:
    rel = "packages/model-runtime/src/core/streams/openai/openai.ts"
    text = _read(rel)
    if "LCA: emit lca.events" in text:
        return False
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
    _write(rel, _replace_once(text, needle, insert, label="openai_stream"))
    return True


def p_qwen_stream() -> bool:
    rel = "packages/model-runtime/src/core/streams/qwen.ts"
    text = _read(rel)
    if "LCA: emit lca.events" in text:
        return False
    needle = "  if (chunk.choices[0]) {"
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

  if (chunk.choices[0]) {"""
    _write(rel, _replace_once(text, needle, insert, label="qwen_stream"))
    return True


def p_protocol() -> bool:
    rel = "packages/model-runtime/src/core/streams/protocol.ts"
    text = _read(rel)
    if "'lca_tool_event'" in text:
        return False
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
    _write(rel, _replace_once(text, anchor, insert, label="protocol"))
    return True


def p_chat_callbacks() -> bool:
    rel = "packages/model-runtime/src/types/chat.ts"
    text = _read(rel)
    if "onLcaToolEvent" in text:
        return False
    anchor = "  onToolsCalling?: (data: {"
    insert = """  /** LCA gateway ``lca.events`` (tool_started / tool_result / tool_state / run_error). */
  onLcaToolEvent?: (event: Record<string, unknown>) => Promise<void> | void;
  onToolsCalling?: (data: {"""
    _write(rel, _replace_once(text, anchor, insert, label="chat_callbacks"))
    return True


def p_fetch_sse() -> bool:
    rel = "packages/fetch-sse/src/fetchSSE.ts"
    text = _read(rel)
    if "lca_tool_event" in text:
        return False
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
    _write(rel, _replace_once(text, anchor, insert, label="fetch_sse"))
    return True


# ── 2. Agent Runtime ──────────────────────────────────────────────────


def p_streaming_types() -> bool:
    rel = "src/store/chat/agents/types/streaming.ts"
    text = _read(rel)
    if "LcaStreamToolEvent" in text:
        return False
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
    return True


def p_streaming_handler() -> bool:
    rel = "src/store/chat/agents/StreamingHandler.ts"
    text = _read(rel)
    if "lcaClosedLoop" in text:
        return False
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
    return True


def p_client_transport() -> bool:
    rel = "src/store/chat/agents/transports/ClientLLMTransport.ts"
    text = _read(rel)
    if "lcaClosedLoop" in text:
        return False
    text = text.replace(
        "        onToolCallsUpdate: (tools) => this.dispatchMessage(assistantMessageId, { tools }),",
        "        onLcaToolEvent: (event) => handler.handleChunk({ event, type: 'lca_tool_event' }),"
        "\n        onToolCallsUpdate: (tools) => this.dispatchMessage(assistantMessageId, { tools }),",
        1,
    )
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
    text = _replace_once(text, anchor, insert, label="client_transport")
    text = text.replace(
        "      toolCalls: result.toolCalls ?? [],\n      toolsCalling: result.tools ?? [],",
        "      lcaClosedLoop: result.lcaClosedLoop,\n      toolCalls: result.toolCalls ?? [],\n      toolsCalling: result.tools ?? [],",
        1,
    )
    _write(rel, text)
    return True


def p_llm_transport_type() -> bool:
    rel = "packages/agent-runtime/src/transport/llm.ts"
    text = _read(rel)
    if "lcaClosedLoop" in text:
        return False
    text = text.replace(
        "  toolCalls: MessageToolCall[];\n  toolsCalling: ChatToolPayload[];",
        "  /** LCA Mode A: skip GeneralChatAgent client tool loop. */\n  lcaClosedLoop?: boolean;\n  toolCalls: MessageToolCall[];\n  toolsCalling: ChatToolPayload[];",
        1,
    )
    _write(rel, text)
    return True


def p_call_llm_finalizer() -> bool:
    rel = "packages/agent-runtime/src/executors/callLlmFinalizer.ts"
    text = _read(rel)
    if "output.lcaClosedLoop" in text:
        return False
    repl = "hasToolsCalling: !output.lcaClosedLoop && output.toolsCalling.length > 0,"
    text = text.replace(
        "hasToolsCalling: output.toolsCalling.length > 0,",
        repl,
    )
    if repl not in text:
        raise SystemExit("[call_llm_finalizer] hasToolsCalling anchor not found")
    _write(rel, text)
    return True


# ── 3. Provider Routing ───────────────────────────────────────────────


def p_default_model() -> bool:
    model = "solo"
    provider = "openai"
    changed = False
    for rel in (
        "packages/business/const/src/llm.ts",
        "apps/desktop/stubs/business-const/src/index.ts",
    ):
        path = UI / rel
        if not path.is_file():
            continue
        text = path.read_text()
        pairs = [
            (r"export const DEFAULT_MODEL = '[^']*';", f"export const DEFAULT_MODEL = '{model}';"),
            (
                r"export const DEFAULT_PROVIDER = '[^']*';",
                f"export const DEFAULT_PROVIDER = '{provider}';",
            ),
            (
                r"export const DEFAULT_MINI_MODEL = '[^']*';",
                f"export const DEFAULT_MINI_MODEL = '{model}';",
            ),
            (
                r"export const DEFAULT_MINI_PROVIDER = '[^']*';",
                f"export const DEFAULT_MINI_PROVIDER = '{provider}';",
            ),
        ]
        for pattern, repl in pairs:
            text, count = re.subn(pattern, repl, text, count=1)
            if count != 1:
                raise SystemExit(f"[default_model] regex failed for {pattern} in {path}")
        path.write_text(text)
        changed = True
    return changed


def p_openai_guard() -> bool:
    rel = "packages/model-runtime/src/providers/openai/index.ts"
    text = _read(rel)
    marker = "/* LCA: solo/team always chat/completions */"
    if marker in text:
        return False
    needle = "      if (isResponsesAPIModel(model) || enabledSearch) {"
    if needle not in text:
        raise SystemExit("[openai_guard] anchor not found")
    replacement = (
        "      const isLcaGatewayModel = ['solo', 'team', 'auto'].includes(model);\n"
        f"      {marker}\n"
        "      if (!isLcaGatewayModel && (isResponsesAPIModel(model) || enabledSearch)) {"
    )
    _write(rel, text.replace(needle, replacement, 1))
    return True


def p_provider_order() -> bool:
    rel = "packages/model-bank/src/modelProviders/index.ts"
    text = _read(rel)
    if "/* LCA: OpenAI first */" in text:
        return False
    needle = "  ...(ENABLE_BUSINESS_FEATURES ? [LobeHubProvider] : []),\n"
    if needle not in text:
        raise SystemExit("[provider_order] LobeHub spread anchor not found")
    text = re.sub(r"\n  OpenAIProvider,\n", "\n", text, count=1)
    text = text.replace(needle, needle + "  OpenAIProvider, /* LCA: OpenAI first */\n", 1)
    _write(rel, text)
    return True


# ── 4. Dev Auth ────────────────────────────────────────────────────────


def p_dev_auth_files() -> bool:
    files = {
        "src/layout/AuthProvider/localDevNoAuth.ts": _LOCAL_DEV_NO_AUTH_TS,
        "src/layout/AuthProvider/LocalDevAuth/LocalDevUserUpdater.tsx": _LOCAL_DEV_USER_UPDATER_TSX,
        "src/layout/AuthProvider/LocalDevAuth/index.tsx": _LOCAL_DEV_AUTH_INDEX_TSX,
    }
    for rel, content in files.items():
        _write(rel, content)
    return True


def p_dev_auth_vite() -> bool:
    rel = "src/layout/AuthProvider/index.vite.tsx"
    text = _read(rel)
    if "LocalDevAuth" in text and "isLocalDevNoAuth" in text:
        return False
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
            return False
        raise SystemExit("[dev_auth_vite] AuthProvider anchor not found")
    _write(rel, text.replace(old, new, 1))
    return True


def p_middleware_mock_user() -> bool:
    rel = "src/libs/next/proxy/define-config.ts"
    text = _read(rel)
    if "ENABLE_MOCK_DEV_USER: skipping session gate" in text:
        return False
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
    _write(rel, _replace_once(text, anchor, insert, label="middleware_mock_user"))
    return True


# ── 5. Route Adaptation ───────────────────────────────────────────────


def p_topic_route() -> bool:
    rel_path = "src/features/AgentSidebar/utils/agentPathname.ts"
    text = _read(rel_path)
    changed = False
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
        text = _replace_once(text, anchor, insert_fn + anchor, label="topic_route_path")
        _write(rel_path, text)
        changed = True

    rel_sync = "src/routes/(main)/agent/features/Conversation/ChatHydration/useChatRouteSync.ts"
    text = _read(rel_sync)
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
        _write(rel_sync, text)
        changed = True

    rel_agent = "src/routes/(main)/agent/_layout/AgentIdSync.tsx"
    text = _read(rel_agent)
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
        _write(rel_agent, text)
        changed = True

    return changed


def p_market_fork() -> bool:
    changed = False
    targets = [
        (
            "src/routes/(main)/community/(detail)/agent/features/Sidebar/ActionButton/ForkAndChat.tsx",
            "let forkResult: { agent:",
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
            """      let actAs: number | undefined;
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

      const forkResult = forkOutcome.data;""",
            """      let forkResult: { agent: { identifier: string; name: string } };
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
      }""",
        ),
        (
            "src/routes/(main)/community/(detail)/group_agent/features/Sidebar/ActionButton/ForkGroupAndChat.tsx",
            "let forkResult: { group:",
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
            """      let actAs: number | undefined;
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
      });""",
            """      let forkResult: { group: { identifier: string } };
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
      }""",
        ),
    ]

    for rel, done_marker, import_anchors, old_fork, new_fork in targets:
        text = _read(rel)
        if done_marker in text or "const localDevFork = isLocalDevNoAuth()" in text:
            continue
        for old_imp, new_imp in import_anchors:
            if old_imp not in text:
                raise SystemExit(f"[market_fork] import anchor not found in {rel}")
            text = text.replace(old_imp, new_imp, 1)
        if old_fork not in text:
            raise SystemExit(f"[market_fork] fork block anchor not found in {rel}")
        text = text.replace(old_fork, new_fork, 1)
        _write(rel, text)
        changed = True

    return changed


# ── 6. Dev UX ──────────────────────────────────────────────────────────


def p_lan_dev() -> bool:
    rel = "src/libs/spaHtml/index.ts"
    text = _read(rel)
    if "VITE_DEV_HOST" in text:
        return False
    candidates = [
        (
            "export const resolveCiteDevOrigin = () =>\n"
            "  `http://localhost:${Number(process.env.VITE_DEV_PORT) || 9876}`;",
            "export const resolveCiteDevOrigin = () => {\n"
            "  const host = process.env.VITE_DEV_HOST || 'localhost';\n"
            "  const port = Number(process.env.VITE_DEV_PORT) || 9876;\n"
            "  return `http://${host}:${port}`;\n"
            "};",
        ),
        (
            "export const resolveCiteDevOrigin = () =>\n"
            "  `http://localhost:${Number(process.env.CITE_DEV_PORT) || 9876}`;",
            "export const resolveCiteDevOrigin = () => {\n"
            "  const host = process.env.VITE_DEV_HOST || 'localhost';\n"
            "  const port = Number(process.env.CITE_DEV_PORT) || 9876;\n"
            "  return `http://${host}:${port}`;\n"
            "};",
        ),
    ]
    for old, new in candidates:
        if old in text:
            _write(rel, text.replace(old, new, 1))
            return True
    raise SystemExit("[lan_dev] resolveCiteDevOrigin anchor not found")


# =======================================================================
#  MANIFEST — ordered patch registry
# =======================================================================

PATCHES: list[PatchMeta] = [
    # ── Streaming Protocol ──
    PatchMeta(
        "openai_stream",
        "Extract lca.events from OpenAI stream chunks",
        ("packages/model-runtime/src/core/streams/openai/openai.ts",),
        "low",
        "streaming",
    ),
    PatchMeta(
        "qwen_stream",
        "Extract lca.events from Qwen stream chunks",
        ("packages/model-runtime/src/core/streams/qwen.ts",),
        "low",
        "streaming",
    ),
    PatchMeta(
        "protocol",
        "Add lca_tool_event to stream protocol dispatch",
        ("packages/model-runtime/src/core/streams/protocol.ts",),
        "low",
        "streaming",
    ),
    PatchMeta(
        "chat_callbacks",
        "Add onLcaToolEvent to ChatStreamCallbacks",
        ("packages/model-runtime/src/types/chat.ts",),
        "low",
        "streaming",
    ),
    PatchMeta(
        "fetch_sse",
        "Handle lca_tool_event in fetchSSE dispatch",
        ("packages/fetch-sse/src/fetchSSE.ts",),
        "low",
        "streaming",
    ),
    # ── Agent Runtime ──
    PatchMeta(
        "streaming_types",
        "Add LcaStreamToolEvent type + closed-loop fields",
        ("src/store/chat/agents/types/streaming.ts",),
        "low",
        "runtime",
    ),
    PatchMeta(
        "streaming_handler",
        "Add handleLcaToolEvent() for tool card UI",
        ("src/store/chat/agents/StreamingHandler.ts",),
        "medium",
        "runtime",
    ),
    PatchMeta(
        "client_transport",
        "Wire onLcaToolEvent callback + error surfacing",
        ("src/store/chat/agents/transports/ClientLLMTransport.ts",),
        "medium",
        "runtime",
    ),
    PatchMeta(
        "llm_transport_type",
        "Add lcaClosedLoop to StreamingResult",
        ("packages/agent-runtime/src/transport/llm.ts",),
        "low",
        "runtime",
    ),
    PatchMeta(
        "call_llm_finalizer",
        "Skip client tool loop when lcaClosedLoop",
        ("packages/agent-runtime/src/executors/callLlmFinalizer.ts",),
        "high",
        "runtime",
    ),
    # ── Provider Routing ──
    PatchMeta(
        "default_model",
        "Set default model/provider to solo/openai",
        ("packages/business/const/src/llm.ts",),
        "low",
        "provider",
    ),
    PatchMeta(
        "openai_guard",
        "LCA virtual models bypass Responses API",
        ("packages/model-runtime/src/providers/openai/index.ts",),
        "medium",
        "provider",
    ),
    PatchMeta(
        "provider_order",
        "Move OpenAI provider to first position",
        ("packages/model-bank/src/modelProviders/index.ts",),
        "low",
        "provider",
    ),
    # ── Dev Auth ──
    PatchMeta(
        "dev_auth_files",
        "Create LocalDevAuth component files",
        (
            "src/layout/AuthProvider/localDevNoAuth.ts",
            "src/layout/AuthProvider/LocalDevAuth/LocalDevUserUpdater.tsx",
            "src/layout/AuthProvider/LocalDevAuth/index.tsx",
        ),
        "low",
        "auth",
    ),
    PatchMeta(
        "dev_auth_vite",
        "Swap BetterAuth for LocalDevAuth in Vite mode",
        ("src/layout/AuthProvider/index.vite.tsx",),
        "medium",
        "auth",
    ),
    PatchMeta(
        "middleware_mock_user",
        "Skip Better Auth session gate for dev",
        ("src/libs/next/proxy/define-config.ts",),
        "medium",
        "auth",
    ),
    # ── Route Adaptation ──
    PatchMeta(
        "topic_route",
        "Stabilize topicId resolution from pathname",
        (
            "src/features/AgentSidebar/utils/agentPathname.ts",
            "src/routes/(main)/agent/features/Conversation/ChatHydration/useChatRouteSync.ts",
            "src/routes/(main)/agent/_layout/AgentIdSync.tsx",
        ),
        "medium",
        "route",
    ),
    PatchMeta(
        "market_fork",
        "Skip Market OIDC on HTTP local dev",
        (
            "src/routes/(main)/community/(detail)/agent/features/Sidebar/ActionButton/ForkAndChat.tsx",
            "src/routes/(main)/community/(detail)/group_agent/features/Sidebar/ActionButton/ForkGroupAndChat.tsx",
        ),
        "low",
        "route",
    ),
    # ── Dev UX ──
    PatchMeta(
        "lan_dev",
        "Use VITE_DEV_HOST for Vite dev asset URLs",
        ("src/libs/spaHtml/index.ts",),
        "low",
        "devux",
    ),
]

_PATCH_FUNCS: dict[str, callable] = {
    "openai_stream": p_openai_stream,
    "qwen_stream": p_qwen_stream,
    "protocol": p_protocol,
    "chat_callbacks": p_chat_callbacks,
    "fetch_sse": p_fetch_sse,
    "streaming_types": p_streaming_types,
    "streaming_handler": p_streaming_handler,
    "client_transport": p_client_transport,
    "llm_transport_type": p_llm_transport_type,
    "call_llm_finalizer": p_call_llm_finalizer,
    "default_model": p_default_model,
    "openai_guard": p_openai_guard,
    "provider_order": p_provider_order,
    "dev_auth_files": p_dev_auth_files,
    "dev_auth_vite": p_dev_auth_vite,
    "middleware_mock_user": p_middleware_mock_user,
    "topic_route": p_topic_route,
    "market_fork": p_market_fork,
    "lan_dev": p_lan_dev,
}

# Verify markers: (file_to_check, marker_string) — read-only check
_VERIFY_MARKERS: dict[str, tuple[str, str]] = {
    "openai_stream": (
        "packages/model-runtime/src/core/streams/openai/openai.ts",
        "LCA: emit lca.events",
    ),
    "qwen_stream": ("packages/model-runtime/src/core/streams/qwen.ts", "LCA: emit lca.events"),
    "protocol": ("packages/model-runtime/src/core/streams/protocol.ts", "'lca_tool_event'"),
    "chat_callbacks": ("packages/model-runtime/src/types/chat.ts", "onLcaToolEvent"),
    "fetch_sse": ("packages/fetch-sse/src/fetchSSE.ts", "lca_tool_event"),
    "streaming_types": ("src/store/chat/agents/types/streaming.ts", "LcaStreamToolEvent"),
    "streaming_handler": ("src/store/chat/agents/StreamingHandler.ts", "lcaClosedLoop"),
    "client_transport": ("src/store/chat/agents/transports/ClientLLMTransport.ts", "lcaClosedLoop"),
    "llm_transport_type": ("packages/agent-runtime/src/transport/llm.ts", "lcaClosedLoop"),
    "call_llm_finalizer": (
        "packages/agent-runtime/src/executors/callLlmFinalizer.ts",
        "output.lcaClosedLoop",
    ),
    "default_model": ("packages/business/const/src/llm.ts", "DEFAULT_MODEL = 'solo'"),
    "openai_guard": (
        "packages/model-runtime/src/providers/openai/index.ts",
        "LCA: solo/team always chat/completions",
    ),
    "provider_order": (
        "packages/model-bank/src/modelProviders/index.ts",
        "/* LCA: OpenAI first */",
    ),
    "dev_auth_files": ("src/layout/AuthProvider/localDevNoAuth.ts", "isLocalDevNoAuth"),
    "dev_auth_vite": ("src/layout/AuthProvider/index.vite.tsx", "LocalDevAuth"),
    "middleware_mock_user": (
        "src/libs/next/proxy/define-config.ts",
        "ENABLE_MOCK_DEV_USER: skipping session gate",
    ),
    "topic_route": (
        "src/features/AgentSidebar/utils/agentPathname.ts",
        "resolveAgentChatRouteTopicId",
    ),
    "market_fork": (
        "src/routes/(main)/community/(detail)/agent/features/Sidebar/ActionButton/ForkAndChat.tsx",
        "isLocalDevNoAuth",
    ),
    "lan_dev": ("src/libs/spaHtml/index.ts", "VITE_DEV_HOST"),
}


# =======================================================================
#  ENGINE
# =======================================================================


def _filter_patches(names: tuple[str, ...]) -> list[PatchMeta]:
    if not names:
        return list(PATCHES)
    selected = []
    for n in names:
        match = [p for p in PATCHES if p.name == n]
        if not match:
            raise SystemExit(f"unknown patch: {n}  (use 'list' to see available)")
        selected.extend(match)
    return selected


def apply_patches(names: tuple[str, ...] = (), *, reset: bool = False) -> list[PatchResult]:
    if not UI.is_dir():
        print("[patch] skip: lobehub-ui/ missing", file=sys.stderr)
        sys.exit(0)
    if reset:
        _clear_stamps()
    patches = _filter_patches(names)
    results: list[PatchResult] = []
    applied_count = 0
    for meta in patches:
        fn = _PATCH_FUNCS[meta.name]
        try:
            was_applied = fn()
        except SystemExit as exc:
            results.append(PatchResult(meta.name, "broken", str(exc)))
            _log("BROKEN", meta.name, str(exc))
            continue
        status = "applied" if was_applied else "skipped"
        if was_applied:
            applied_count += 1
        results.append(PatchResult(meta.name, status))
        _log(status.upper(), meta.name)
    _write_stamp(results)
    print(f"\n[patch] done: {applied_count} applied, {len(results) - applied_count} skipped")
    return results


def verify_patches(names: tuple[str, ...] = ()) -> list[PatchResult]:
    if not UI.is_dir():
        print("[verify] skip: lobehub-ui/ missing", file=sys.stderr)
        sys.exit(0)
    patches = _filter_patches(names)
    results: list[PatchResult] = []
    ok_count = 0
    broken_count = 0
    for meta in patches:
        marker_info = _VERIFY_MARKERS.get(meta.name)
        if not marker_info:
            results.append(PatchResult(meta.name, "ok", "no verify marker (skipped)"))
            _log("SKIP", meta.name, "no verify marker")
            continue
        check_file, marker_str = marker_info
        path = UI / check_file
        if not path.is_file():
            results.append(PatchResult(meta.name, "missing_file", f"{check_file} not found"))
            _log("MISS", meta.name, f"{check_file} not found")
            broken_count += 1
            continue
        text = path.read_text()
        if marker_str in text:
            results.append(PatchResult(meta.name, "ok", "marker present"))
            _log("OK", meta.name)
            ok_count += 1
        else:
            results.append(PatchResult(meta.name, "broken", f"marker absent in {check_file}"))
            _log("BROKEN", meta.name, f"marker absent in {check_file}")
            broken_count += 1
    print(f"\n[verify] {ok_count} ok, {broken_count} broken/missing")
    return results


def list_patches() -> None:
    print(f"{'#':>2}  {'Name':<24} {'Risk':<6} {'Category':<10} Description")
    print("─" * 90)
    for i, meta in enumerate(PATCHES, 1):
        print(f"{i:>2}  {meta.name:<24} {meta.risk:<6} {meta.category:<10} {meta.description}")
    print(f"\nTotal: {len(PATCHES)} patches across {len({m.category for m in PATCHES})} categories")
    print("Target: lobehub-ui/ (LobeHub v2.2.13)")


# ── Helpers ────────────────────────────────────────────────────────────


def _check_files(files: tuple[str, ...]) -> str:
    for rel in files:
        if not (UI / rel).is_file():
            return "missing"
    return "ok"


def _clear_stamps() -> None:
    for f in UI.glob(".lca-*-patched"):
        f.unlink()
    if STAMP_FILE.is_file():
        STAMP_FILE.unlink()


def _write_stamp(results: list[PatchResult]) -> None:
    stamp = {
        "patched_at": datetime.now(timezone.utc).isoformat(),
        "patches": {r.name: r.status for r in results},
        "lobehub_release": _read_origin_release(),
    }
    STAMP_FILE.write_text(json.dumps(stamp, indent=2, ensure_ascii=False) + "\n")


def _read_origin_release() -> str:
    origin = UI / ".lca-origin.json"
    if origin.is_file():
        try:
            return json.loads(origin.read_text()).get("release", "unknown")
        except (json.JSONDecodeError, KeyError):
            pass
    return "unknown"


# =======================================================================
#  CLI
# =======================================================================


def main() -> None:
    args = sys.argv[1:]
    cmd = "apply"
    names: list[str] = []
    reset = False

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("apply", "verify", "list"):
            cmd = a
        elif a == "--reset":
            reset = True
        elif a in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            names.append(a)
        i += 1

    if cmd == "list":
        list_patches()
    elif cmd == "verify":
        results = verify_patches(tuple(names))
        broken = [r for r in results if r.status == "broken"]
        sys.exit(1 if broken else 0)
    else:
        results = apply_patches(tuple(names), reset=reset)
        broken = [r for r in results if r.status == "broken"]
        sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
