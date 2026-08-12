#!/usr/bin/env python3
"""Unified LCA ↔ LobeHub patch engine.

Single entry point for all LobeHub source customizations:
  apply    — idempotent patch application (default)
  verify   — dry-run anchor/marker check for upgrade compatibility
  list     — print patch manifest
  drift    — detect unregistered source modifications (enforcement)
  manifest — generate structured JSON manifest of all patches
  doctor   — run all health checks (verify + drift + consistency)

Usage:
  python3 deploy/lobehub/patch_lobehub.py              # apply all
  python3 deploy/lobehub/patch_lobehub.py verify       # check anchors
  python3 deploy/lobehub/patch_lobehub.py list         # show manifest
  python3 deploy/lobehub/patch_lobehub.py drift        # detect unregistered edits
  python3 deploy/lobehub/patch_lobehub.py manifest     # JSON manifest
  python3 deploy/lobehub/patch_lobehub.py doctor       # full health check
  python3 deploy/lobehub/patch_lobehub.py apply openai_stream protocol  # specific

Rules:
  1. NEVER edit lobehub-ui/ directly — always via patches
  2. Every modification must be registered as a patch function
  3. Run `drift` after development to catch unregistered changes
  4. Run `doctor` before committing to verify full health
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
    depends_on: tuple[str, ...] = ()
    why: str = ""
    technical_detail: str = ""


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


def p_lca_tool_result_merge() -> bool:
    """Upgrade LCA tool SSE handler — ChatToolResult shape for LobeHub tool cards."""
    rel = "src/store/chat/agents/StreamingHandler.ts"
    text = _read(rel)
    if "mergeLcaToolResult" in text:
        return False
    if "handleLcaToolEvent" not in text:
        return False
    text = text.replace(
        "  type ChatToolPayload,\n  type MessageContentPart,",
        "  type ChatToolPayload,\n  type ChatToolResult,\n  type MessageContentPart,",
        1,
    )
    old_handler = """  private handleLcaToolEvent(event: LcaStreamToolEvent): void {
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
  }"""
    new_handler = """  private mergeLcaToolResult(
    existing: ChatToolPayload,
    patch: {
      content?: string;
      error?: string;
      state?: Record<string, unknown>;
    },
  ): ChatToolPayload {
    const prev: ChatToolResult =
      existing.result &&
      typeof existing.result === 'object' &&
      existing.result !== null &&
      'content' in existing.result
        ? (existing.result as ChatToolResult)
        : typeof existing.result === 'string'
          ? { content: existing.result, id: existing.id }
          : { content: '', id: existing.id };
    const mergedState = {
      ...(prev.state ?? {}),
      ...(patch.state ?? {}),
    };
    const streamText =
      patch.content ||
      (typeof mergedState.output === 'string' ? mergedState.output : '') ||
      (typeof mergedState.stdout === 'string' ? mergedState.stdout : '') ||
      prev.content ||
      '';
    return {
      ...existing,
      result: {
        id: prev.id ?? existing.id,
        content: streamText,
        error: patch.error ?? prev.error,
        state: Object.keys(mergedState).length > 0 ? mergedState : prev.state,
      },
    };
  }

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
      const content =
        event.type === 'tool_result'
          ? event.content
          : 'content' in event
            ? (event as { content?: string }).content
            : undefined;
      const updated = this.mergeLcaToolResult(existing, {
        content,
        error: event.type === 'tool_result' ? event.error : undefined,
        state: event.state,
      });
      this.lcaToolsById.set(event.tool_call_id, updated);
      this.tools = [...this.lcaToolsById.values()];
      this.callbacks.onToolCallsUpdate(this.tools);
    }
  }"""
    if old_handler not in text:
        return False
    text = text.replace(old_handler, new_handler, 1)
    _write(rel, text)
    return True


def p_lca_streaming_types() -> bool:
    """Extend LCA stream tool event types for live sandbox stdout."""
    rel = "src/store/chat/agents/types/streaming.ts"
    text = _read(rel)
    if "tool_state_content" in text:
        return False
    text = text.replace(
        """  | {
      snapshot_seq?: number;
      state: Record<string, unknown>;
      tool_call_id: string;
      type: 'tool_state';
    }""",
        """  | {
      content?: string;
      snapshot_seq?: number;
      state: Record<string, unknown>;
      tool_call_id: string;
      type: 'tool_state';
    }""",
        1,
    )
    text = text.replace(
        """  | {
      closed_loop?: boolean;
      content?: string;
      error?: string;
      state?: Record<string, unknown>;
      tool_call_id: string;
      type: 'tool_result';
    }""",
        """  | {
      closed_loop?: boolean;
      content?: string;
      error?: string;
      files?: Array<Record<string, unknown>>;
      state?: Record<string, unknown>;
      tool_call_id: string;
      type: 'tool_result';
    }""",
        1,
    )
    if "tool_state_content" not in text:
        text = text.replace(
            "export type LcaStreamToolEvent =",
            "// tool_state_content: LCA sandbox live stdout\nexport type LcaStreamToolEvent =",
            1,
        )
    _write(rel, text)
    return True


def p_sandbox_generated_files() -> bool:
    """Show harvested sandbox files on executeCode tool cards."""
    rel = "packages/builtin-tool-cloud-sandbox/src/client/Render/ExecuteCode/index.tsx"
    text = _read(rel)
    if "GeneratedFilesStrip" in text:
        return False
    text = text.replace(
        "import { Block, Flexbox, Highlighter } from '@lobehub/ui';",
        "import { Block, Flexbox, Highlighter, Text } from '@lobehub/ui';\nimport { Button } from 'antd';",
        1,
    )
    insert = """
interface GeneratedFilePart {
  attachmentId?: string;
  mimeType?: string;
  name?: string;
  previewable?: boolean;
  url?: string;
}

const GeneratedFilesStrip = memo<{ files?: GeneratedFilePart[] }>(({ files }) => {
  if (!files?.length) return null;
  return (
    <Flexbox gap={4}>
      <Text style={{ fontSize: 12, opacity: 0.65 }}>Generated files</Text>
      <Flexbox gap={4} horizontal wrap>
        {files.map((file) => {
          const label = file.name || 'file';
          const href = file.url;
          if (!href) return null;
          return (
            <Button
              href={href}
              key={`${label}-${href}`}
              rel="noopener noreferrer"
              size="small"
              target="_blank"
              type={file.previewable ? 'primary' : 'default'}
            >
              {label}
            </Button>
          );
        })}
      </Flexbox>
    </Flexbox>
  );
});

GeneratedFilesStrip.displayName = 'GeneratedFilesStrip';
"""
    text = text.replace(
        "const styles = createStaticStyles(({ css }) => ({",
        insert + "\nconst styles = createStaticStyles(({ css }) => ({",
        1,
    )
    text = text.replace(
        "          {pluginState?.stderr && (\n            <Highlighter wrap language={'text'} showLanguage={false} variant={'filled'}>\n              {pluginState.stderr}\n            </Highlighter>\n          )}\n        </Block>",
        "          {pluginState?.stderr && (\n            <Highlighter wrap language={'text'} showLanguage={false} variant={'filled'}>\n              {pluginState.stderr}\n            </Highlighter>\n          )}\n          <GeneratedFilesStrip files={(pluginState as { files?: GeneratedFilePart[] })?.files} />\n        </Block>",
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


def p_turbopack_dev() -> bool:
    rel = "scripts/devStartupSequence.mts"
    text = _read(rel)
    if "'--turbo'" in text:
        return False
    old = "spawn('bunx', ['next', 'dev', '-p', String(nextPort)]"
    new = "spawn('bunx', ['next', 'dev', '--turbo', '-p', String(nextPort)]"
    _write(rel, _replace_once(text, old, new, label="turbopack_dev"))
    return True


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


# ── 6. File Proxy & Reasoning Segmentation ───────────────────────────


def p_file_proxy_rewrite() -> bool:
    """Add /files/* rewrite to next.config.ts → LCA gateway for artifact downloads."""
    rel = "next.config.ts"
    text = _read(rel)
    if "LCA: file proxy" in text:
        return False
    old = "const nextConfig = defineConfig({"
    new = "const _baseConfig = defineConfig({"
    if old not in text:
        return False
    text = text.replace(old, new, 1)
    old_end = "});\n\nexport default nextConfig;"
    new_end = """});

// LCA: file proxy — artifact downloads via Next.js rewrite → LCA gateway
const nextConfig = {
  ..._baseConfig,
  async rewrites() {
    const base = process.env.LCA_GATEWAY_PUBLIC_URL || 'http://127.0.0.1:8765';
    const baseRewrites = typeof _baseConfig.rewrites === 'function'
      ? await _baseConfig.rewrites()
      : [];
    return [
      ...(Array.isArray(baseRewrites) ? baseRewrites : []),
      {
        source: '/files/:path*',
        destination: `${base.replace(/\\/$/, '')}/files/:path*`,
      },
    ];
  },
};

export default nextConfig;"""
    if old_end not in text:
        return False
    text = text.replace(old_end, new_end, 1)
    _write(rel, text)
    return True


def p_reasoning_segmentation() -> bool:
    """Handle reasoning_start/end LCA events for per-step thinking blocks."""
    # Step 1: Add reasoning types to LcaStreamToolEvent
    rel_types = "src/store/chat/agents/types/streaming.ts"
    text_types = _read(rel_types)
    if "'reasoning_start'" not in text_types:
        # Add reasoning event types to the LcaStreamToolEvent union
        type_anchor = (
            "  | { closed_loop?: boolean; code?: string; message: string; type: 'run_error' };"
        )
        type_insert = """  | { closed_loop?: boolean; code?: string; message: string; type: 'run_error' }
  // LCA: per-step reasoning boundaries (gateway emits reasoning_start/end per LLM call)
  | { step: number; type: 'reasoning_start' }
  | { step: number; type: 'reasoning_end' };"""
        if type_anchor not in text_types:
            raise SystemExit("[reasoning_segmentation] type anchor not found in streaming.ts")
        text_types = text_types.replace(type_anchor, type_insert, 1)
        _write(rel_types, text_types)

    # Step 2: Add handling in StreamingHandler
    rel = "src/store/chat/agents/StreamingHandler.ts"
    text = _read(rel)
    if "'reasoning_start'" in text:
        return False
    if "handleLcaToolEvent" not in text:
        return False
    anchor = """  private handleLcaToolEvent(event: LcaStreamToolEvent): void {
    if (event.type === 'run_error') {"""
    insert = """  private handleLcaToolEvent(event: LcaStreamToolEvent): void {
    // LCA: per-step reasoning segmentation
    if (event.type === 'reasoning_start') {
      this.endReasoningIfNeeded();
      return;
    }
    if (event.type === 'reasoning_end') {
      this.endReasoningIfNeeded();
      return;
    }

    if (event.type === 'run_error') {"""
    if anchor not in text:
        return False
    text = text.replace(anchor, insert, 1)
    _write(rel, text)
    return True


def p_tool_result_files() -> bool:
    """Pass files[] from tool_result events into ChatToolResult state."""
    rel = "src/store/chat/agents/StreamingHandler.ts"
    text = _read(rel)
    if "mergeLcaToolResult" not in text:
        return False
    if "event.files" in text:
        return False
    anchor = """      const updated = this.mergeLcaToolResult(existing, {
        content,
        error: event.type === 'tool_result' ? event.error : undefined,
        state: event.state,
      });"""
    replacement = """      const updated = this.mergeLcaToolResult(existing, {
        content,
        error: event.type === 'tool_result' ? event.error : undefined,
        state: {
          ...event.state,
          // LCA: pass files[] from tool_result into card state
          ...(event.type === 'tool_result' && 'files' in event && event.files
            ? { files: event.files }
            : {}),
        },
      });"""
    if anchor not in text:
        return False
    text = text.replace(anchor, replacement, 1)
    _write(rel, text)
    return True


def p_reasoning_section_type() -> bool:
    """Add reasoning_section type to LcaStreamToolEvent union."""
    rel = "src/store/chat/agents/types/streaming.ts"
    text = _read(rel)
    if "reasoning_section" in text:
        return False
    anchor = "  | { step: number; type: 'reasoning_end' };"
    if anchor not in text:
        raise SystemExit(
            "[reasoning_section_type] anchor not found — run after reasoning_segmentation"
        )
    replacement = (
        "  | { step: number; type: 'reasoning_end' }\n"
        "  // LCA: completed reasoning section — carries full text for one LLM turn\n"
        "  | { content: string; step: number; type: 'reasoning_section' };"
    )
    text = text.replace(anchor, replacement, 1)
    _write(rel, text)
    return True


def p_reasoning_section_handler() -> bool:
    """Add completedReasoningSections state + multi-section logic to StreamingHandler.

    8 modifications:
      1. completedReasoningSections field
      2. getThinkingContent() combines sections
      3. handleReasoningChunk() multimodal branching
      4. reasoning_section handler in handleLcaToolEvent()
      5. notifyContentPartUpdate() multi-section
      6. buildReasoningState() combined sections
      7. buildFinalResult() combined sections + multimodal
    """
    rel = "src/store/chat/agents/StreamingHandler.ts"
    text = _read(rel)
    if "completedReasoningSections" in text:
        return False

    # 1. Add completedReasoningSections field
    anchor1 = "  private reasoningParts: MessageContentPart[] = [];\n\n  // ========== Multimodal state =========="
    if anchor1 not in text:
        raise SystemExit("[reasoning_section_handler] anchor1 not found")
    text = text.replace(
        anchor1,
        "  private reasoningParts: MessageContentPart[] = [];\n"
        "  // Completed reasoning sections — each LLM turn's thinking is saved here\n"
        "  // when a reasoning_section event arrives from the backend. This enables\n"
        "  // separate collapsible blocks per step.\n"
        "  private completedReasoningSections: { content: string; duration: number; step: number }[] = [];\n"
        "\n  // ========== Multimodal state ==========",
        1,
    )

    # 2. getThinkingContent() combines sections
    anchor2 = "  getThinkingContent(): string {\n    return this.thinkingContent;\n  }"
    if anchor2 not in text:
        raise SystemExit("[reasoning_section_handler] anchor2 not found")
    text = text.replace(
        anchor2,
        "  getThinkingContent(): string {\n"
        "    const sections = this.completedReasoningSections.map((s) => s.content);\n"
        "    if (this.thinkingContent) sections.push(this.thinkingContent);\n"
        "    return sections.join('\\n\\n');\n"
        "  }",
        1,
    )

    # 3. handleReasoningChunk() multimodal branching
    anchor3 = "    this.thinkingContent += chunk.text;\n\n    this.callbacks.onReasoningUpdate({ content: this.thinkingContent });\n  }"
    if anchor3 not in text:
        raise SystemExit("[reasoning_section_handler] anchor3 not found")
    text = text.replace(
        anchor3,
        "    this.thinkingContent += chunk.text;\n"
        "\n"
        "    // When we have completed reasoning sections, use multimodal format\n"
        "    // so the frontend renders each section as a separate block.\n"
        "    if (this.completedReasoningSections.length > 0) {\n"
        "      const parts: MessageContentPart[] = this.completedReasoningSections.map(\n"
        "        (s) => ({ text: s.content, type: 'text' as const }),\n"
        "      );\n"
        "      if (this.thinkingContent) {\n"
        "        parts.push({ text: this.thinkingContent, type: 'text' as const });\n"
        "      }\n"
        "      const totalDuration =\n"
        "        this.completedReasoningSections.reduce((sum, s) => sum + (s.duration || 0), 0) +\n"
        "        (this.thinkingDuration || 0);\n"
        "      this.callbacks.onContentUpdate(this.output, {\n"
        "        duration: totalDuration || undefined,\n"
        "        isMultimodal: true,\n"
        "        tempDisplayContent: parts,\n"
        "      });\n"
        "    } else {\n"
        "      this.callbacks.onReasoningUpdate({ content: this.thinkingContent });\n"
        "    }\n"
        "  }",
        1,
    )

    # 4. reasoning_section handler in handleLcaToolEvent()
    anchor4 = (
        "    if (event.type === 'reasoning_end') {\n"
        "      this.endReasoningIfNeeded();\n"
        "      return;\n"
        "    }\n"
        "\n"
        "    if (event.type === 'run_error') {"
    )
    if anchor4 not in text:
        raise SystemExit("[reasoning_section_handler] anchor4 not found")
    text = text.replace(
        anchor4,
        "    if (event.type === 'reasoning_end') {\n"
        "      this.endReasoningIfNeeded();\n"
        "      return;\n"
        "    }\n"
        "    // LCA: reasoning_section — a completed reasoning block from one LLM turn.\n"
        "    // Save the current thinking content as a finished section, then reset\n"
        "    // state so the next step's reasoning starts a fresh block.\n"
        "    if (event.type === 'reasoning_section') {\n"
        "      const sectionEvent = event as { content: string; step: number; type: 'reasoning_section' };\n"
        "      this.endReasoningIfNeeded();\n"
        "      const duration = this.thinkingDuration || 0;\n"
        "      this.completedReasoningSections.push({\n"
        "        content: sectionEvent.content,\n"
        "        duration,\n"
        "        step: sectionEvent.step,\n"
        "      });\n"
        "      this.reasoningParts = [\n"
        "        ...this.reasoningParts,\n"
        "        { text: sectionEvent.content, type: 'text' },\n"
        "      ];\n"
        "      this.thinkingContent = '';\n"
        "      this.thinkingStartAt = undefined;\n"
        "      this.thinkingDuration = undefined;\n"
        "      const totalDuration = this.completedReasoningSections.reduce(\n"
        "        (sum, s) => sum + (s.duration || 0),\n"
        "        0,\n"
        "      );\n"
        "      this.callbacks.onContentUpdate(\n"
        "        this.output,\n"
        "        {\n"
        "          duration: totalDuration || undefined,\n"
        "          isMultimodal: true,\n"
        "          tempDisplayContent: this.reasoningParts,\n"
        "        },\n"
        "      );\n"
        "      return;\n"
        "    }\n"
        "\n"
        "    if (event.type === 'run_error') {",
        1,
    )

    # 5. notifyContentPartUpdate() multi-section
    anchor5 = (
        "  private notifyContentPartUpdate(): void {\n"
        "    const hasContentImages = this.contentParts.some((p) => p.type === 'image');\n"
        "    const hasReasoningImages = this.reasoningParts.some((p) => p.type === 'image');\n"
        "\n"
        "    this.callbacks.onContentUpdate(\n"
        "      this.output,\n"
        "      hasReasoningImages\n"
        "        ? {\n"
        "            duration: this.thinkingDuration,\n"
        "            isMultimodal: true,\n"
        "            tempDisplayContent: this.reasoningParts,\n"
        "          }\n"
        "        : this.thinkingContent\n"
        "          ? { content: this.thinkingContent, duration: this.thinkingDuration }\n"
        "          : undefined,"
    )
    if anchor5 not in text:
        raise SystemExit("[reasoning_section_handler] anchor5 not found")
    text = text.replace(
        anchor5,
        "  private notifyContentPartUpdate(): void {\n"
        "    const hasContentImages = this.contentParts.some((p) => p.type === 'image');\n"
        "    const hasReasoningImages = this.reasoningParts.some((p) => p.type === 'image');\n"
        "    const hasMultipleReasoningSections =\n"
        "      this.completedReasoningSections.length > 0 || hasReasoningImages;\n"
        "    const allReasoningContents = this.completedReasoningSections.map((s) => s.content);\n"
        "    if (this.thinkingContent) allReasoningContents.push(this.thinkingContent);\n"
        "    const combinedReasoning = allReasoningContents.join('\\n\\n');\n"
        "    const totalReasoningDuration =\n"
        "      this.completedReasoningSections.reduce((sum, s) => sum + (s.duration || 0), 0) +\n"
        "      (this.thinkingDuration || 0);\n"
        "\n"
        "    this.callbacks.onContentUpdate(\n"
        "      this.output,\n"
        "      hasMultipleReasoningSections\n"
        "        ? {\n"
        "            duration: totalReasoningDuration || undefined,\n"
        "            isMultimodal: true,\n"
        "            tempDisplayContent: this.reasoningParts,\n"
        "          }\n"
        "        : combinedReasoning\n"
        "          ? { content: combinedReasoning, duration: totalReasoningDuration || undefined }\n"
        "          : undefined,",
        1,
    )

    # 6. buildReasoningState() combined sections
    anchor6 = (
        "  private buildReasoningState(): ReasoningState | undefined {\n"
        "    if (!this.thinkingContent) return undefined;\n"
        "    return { content: this.thinkingContent, duration: this.thinkingDuration };\n"
        "  }"
    )
    if anchor6 not in text:
        raise SystemExit("[reasoning_section_handler] anchor6 not found")
    text = text.replace(
        anchor6,
        "  private buildReasoningState(): ReasoningState | undefined {\n"
        "    const sections = this.completedReasoningSections.map((s) => s.content);\n"
        "    if (this.thinkingContent) sections.push(this.thinkingContent);\n"
        "    const combined = sections.join('\\n\\n');\n"
        "    if (!combined) return undefined;\n"
        "    const totalDuration =\n"
        "      this.completedReasoningSections.reduce((sum, s) => sum + (s.duration || 0), 0) +\n"
        "      (this.thinkingDuration || 0);\n"
        "    return { content: combined, duration: totalDuration || undefined };\n"
        "  }",
        1,
    )

    # 7. buildFinalResult() combined sections
    anchor7 = (
        "    // Determine final reasoning content\n"
        "    const finalDuration =\n"
        "      this.thinkingDuration && !isNaN(this.thinkingDuration) ? this.thinkingDuration : undefined;\n"
        "\n"
        "    // Get signature from finishData.reasoning (provided by backend in onFinish)\n"
        "    const reasoningSignature = finishData.reasoning?.signature;\n"
        "    // Hidden Responses reasoning items stay replayable without any visible content\n"
        "    const hasResponseItems = !!finishData.reasoning?.responseItems?.length;\n"
        "\n"
        "    let finalReasoning: ReasoningState | undefined;\n"
        "    if (hasReasoningImages) {\n"
        "      finalReasoning = {\n"
        "        content: serializePartsForStorage(this.reasoningParts),\n"
        "        duration: finalDuration,\n"
        "        isMultimodal: true,\n"
        "        signature: reasoningSignature,\n"
        "      };\n"
        "    } else if (this.thinkingContent) {\n"
        "      finalReasoning = {\n"
        "        ...finishData.reasoning,\n"
        "        content: this.thinkingContent,\n"
        "        duration: finalDuration,\n"
        "      };\n"
        "    } else if (finishData.reasoning?.content || reasoningSignature || hasResponseItems) {"
    )
    if anchor7 not in text:
        raise SystemExit("[reasoning_section_handler] anchor7 not found")
    text = text.replace(
        anchor7,
        "    // If there are multiple reasoning sections, add any remaining\n"
        "    // thinkingContent as a final reasoningPart\n"
        "    if (this.completedReasoningSections.length > 0 && this.thinkingContent) {\n"
        "      this.reasoningParts = [\n"
        "        ...this.reasoningParts,\n"
        "        { text: this.thinkingContent, type: 'text' },\n"
        "      ];\n"
        "    }\n"
        "\n"
        "    // Determine final reasoning content — combine all completed sections\n"
        "    const allSectionContents = this.completedReasoningSections.map((s) => s.content);\n"
        "    if (this.thinkingContent) allSectionContents.push(this.thinkingContent);\n"
        "    const combinedThinkingContent = allSectionContents.join('\\n\\n');\n"
        "\n"
        "    const allSectionDurations = this.completedReasoningSections.map((s) => s.duration);\n"
        "    if (this.thinkingDuration && !isNaN(this.thinkingDuration)) {\n"
        "      allSectionDurations.push(this.thinkingDuration);\n"
        "    }\n"
        "    const finalDuration =\n"
        "      allSectionDurations.length > 0\n"
        "        ? allSectionDurations.reduce((sum, d) => sum + (d || 0), 0)\n"
        "        : undefined;\n"
        "\n"
        "    // Get signature from finishData.reasoning (provided by backend in onFinish)\n"
        "    const reasoningSignature = finishData.reasoning?.signature;\n"
        "    // Hidden Responses reasoning items stay replayable without any visible content\n"
        "    const hasResponseItems = !!finishData.reasoning?.responseItems?.length;\n"
        "    const hasMultipleReasoningSections =\n"
        "      this.completedReasoningSections.length > 0 || hasReasoningImages;\n"
        "\n"
        "    let finalReasoning: ReasoningState | undefined;\n"
        "    if (hasMultipleReasoningSections) {\n"
        "      finalReasoning = {\n"
        "        content: serializePartsForStorage(this.reasoningParts),\n"
        "        duration: finalDuration,\n"
        "        isMultimodal: true,\n"
        "        signature: reasoningSignature,\n"
        "      };\n"
        "    } else if (combinedThinkingContent) {\n"
        "      finalReasoning = {\n"
        "        ...finishData.reasoning,\n"
        "        content: combinedThinkingContent,\n"
        "        duration: finalDuration,\n"
        "      };\n"
        "    } else if (finishData.reasoning?.content || reasoningSignature || hasResponseItems) {",
        1,
    )

    _write(rel, text)
    return True


def p_desktop_default_model() -> bool:
    """Set default model/provider in desktop stubs to solo/openai."""
    rel = "apps/desktop/stubs/business-const/src/index.ts"
    text = _read(rel)
    if "DEFAULT_MODEL = 'solo'" in text:
        return False
    text = text.replace(
        "export const DEFAULT_MINI_MODEL = 'gpt-5.4-mini';",
        "export const DEFAULT_MINI_MODEL = 'solo';",
        1,
    )
    text = text.replace(
        "export const DEFAULT_MODEL = 'deepseek-v4-pro';", "export const DEFAULT_MODEL = 'solo';", 1
    )
    text = text.replace(
        "export const DEFAULT_PROVIDER = 'deepseek';",
        "export const DEFAULT_PROVIDER = 'openai';",
        1,
    )
    _write(rel, text)
    return True


def p_topic_route_test() -> bool:
    """Add test for resolveAgentChatRouteTopicId (companion to topic_route patch)."""
    rel = "src/features/AgentSidebar/utils/agentPathname.test.ts"
    text = _read(rel)
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
    _write(rel, text)
    return True


def p_reasoning_multi_block() -> bool:
    """Render multiple <Thinking> components when reasoning has multiple sections.

    Upstream Reasoning.tsx renders all reasoning parts in a single <Thinking>
    Accordion. This patch changes it to render one <Thinking> per section
    when isMultimodal + tempDisplayContent contains multiple text parts —
    matching LobeHub's native per-operation reasoning display.
    """
    rel = "src/features/Conversation/Messages/components/Reasoning.tsx"
    text = _read(rel)
    if "LCA: multi-block reasoning" in text:
        return False

    old_body = (
        "const Reasoning = memo<ReasoningProps>(\n"
        "  ({ content = '', duration, id, isMultimodal, tempDisplayContent }) => {\n"
        "    const isReasoning = useConversationStore(messageStateSelectors.isMessageInReasoning(id));\n"
        "    const transitionMode = useUserStore(userGeneralSettingsSelectors.transitionMode);\n"
        "\n"
        "    const parts = tempDisplayContent || deserializeParts(content);\n"
        "\n"
        "    // If parts are provided, render multimodal content\n"
        "    const thinkingContent = isMultimodal && parts ? <RichContentRenderer parts={parts} /> : content;\n"
        "\n"
        "    return (\n"
        "      <Thinking\n"
        "        content={thinkingContent}\n"
        "        duration={duration}\n"
        "        thinking={isReasoning}\n"
        "        thinkingAnimated={transitionMode === 'fadeIn' && isReasoning}\n"
        "      />\n"
        "    );\n"
        "  },\n"
        ");"
    )
    if old_body not in text:
        raise SystemExit("[reasoning_multi_block] anchor not found")

    new_body = (
        "const Reasoning = memo<ReasoningProps>(\n"
        "  ({ content = '', duration, id, isMultimodal, tempDisplayContent }) => {\n"
        "    const isReasoning = useConversationStore(messageStateSelectors.isMessageInReasoning(id));\n"
        "    const transitionMode = useUserStore(userGeneralSettingsSelectors.transitionMode);\n"
        "\n"
        "    const parts = tempDisplayContent || deserializeParts(content);\n"
        "\n"
        "    // LCA: multi-block reasoning — when we have multiple text parts from\n"
        "    // completed reasoning sections, render each as a separate <Thinking>\n"
        "    // Accordion so each LLM turn gets its own collapsible block.\n"
        "    const textParts = isMultimodal && parts\n"
        "      ? parts.filter((p) => p.type === 'text' && 'text' in p && p.text)\n"
        "      : [];\n"
        "\n"
        "    if (textParts.length > 1) {\n"
        "      return (\n"
        "        <>\n"
        "          {textParts.map((part, idx) => {\n"
        "            const partText = 'text' in part ? (part.text as string) : '';\n"
        "            const isLast = idx === textParts.length - 1;\n"
        "            return (\n"
        "              <Thinking\n"
        "                content={partText}\n"
        "                duration={duration}\n"
        "                key={idx}\n"
        "                thinking={isLast && isReasoning}\n"
        "                thinkingAnimated={isLast && transitionMode === 'fadeIn' && isReasoning}\n"
        "              />\n"
        "            );\n"
        "          })}\n"
        "        </>\n"
        "      );\n"
        "    }\n"
        "\n"
        "    // Single-block fallback — original upstream behavior\n"
        "    const thinkingContent = isMultimodal && parts ? <RichContentRenderer parts={parts} /> : content;\n"
        "\n"
        "    return (\n"
        "      <Thinking\n"
        "        content={thinkingContent}\n"
        "        duration={duration}\n"
        "        thinking={isReasoning}\n"
        "        thinkingAnimated={transitionMode === 'fadeIn' && isReasoning}\n"
        "      />\n"
        "    );\n"
        "  },\n"
        ");"
    )
    text = text.replace(old_body, new_body, 1)
    _write(rel, text)
    return True


# =======================================================================
#  MANIFEST — ordered patch registry
# =======================================================================

PATCHES: list[PatchMeta] = [
    # ── Streaming Protocol ──────────────────────────────────────────────
    # LCA Gateway embeds tool lifecycle events in the standard OpenAI SSE
    # stream via a `lca: { events: [...] }` extension field. These patches
    # make LobeHub's stream transformers extract and dispatch those events.
    PatchMeta(
        "openai_stream",
        "Extract lca.events from OpenAI stream chunks",
        ("packages/model-runtime/src/core/streams/openai/openai.ts",),
        "low",
        "streaming",
        why="LCA Gateway embeds tool events in OpenAI SSE; LobeHub must extract them",
        technical_detail=(
            "Insert lca.events extraction at the top of transformOpenAIStream. "
            "Each event is emitted as a StreamProtocolChunk with type 'lca_tool_event'."
        ),
    ),
    PatchMeta(
        "qwen_stream",
        "Extract lca.events from Qwen stream chunks",
        ("packages/model-runtime/src/core/streams/qwen.ts",),
        "low",
        "streaming",
        why="Qwen provider has its own stream transformer; needs same extraction",
        technical_detail=(
            "Same logic as openai_stream but in transformQwenStream. "
            "Needed when QWEN_PROXY_URL points to LCA gateway."
        ),
    ),
    PatchMeta(
        "protocol",
        "Add lca_tool_event to stream protocol dispatch",
        ("packages/model-runtime/src/core/streams/protocol.ts",),
        "low",
        "streaming",
        depends_on=("openai_stream", "qwen_stream"),
        why="Protocol dispatcher must recognize the new chunk type",
        technical_detail=(
            "Add 'lca_tool_event' to StreamProtocolChunk type union and "
            "switch case to call callbacks.onLcaToolEvent."
        ),
    ),
    PatchMeta(
        "chat_callbacks",
        "Add onLcaToolEvent to ChatStreamCallbacks",
        ("packages/model-runtime/src/types/chat.ts",),
        "low",
        "streaming",
        why="Callback interface needs the new method signature",
        technical_detail="Add onLcaToolEvent?: (event: Record<string, unknown>) => void to ChatStreamCallbacks.",
    ),
    PatchMeta(
        "fetch_sse",
        "Handle lca_tool_event in fetchSSE dispatch",
        ("packages/fetch-sse/src/fetchSSE.ts",),
        "low",
        "streaming",
        depends_on=("protocol",),
        why="fetchSSE is the low-level SSE consumer; must forward lca_tool_event",
        technical_detail="Add 'lca_tool_event' case to the onMessageHandle type union and switch dispatch.",
    ),
    # ── Agent Runtime ───────────────────────────────────────────────────
    # Frontend state management for LCA's server-side tool execution model.
    # LCA runs tools server-side (closed-loop), so the client must NOT
    # initiate its own tool call loop.
    PatchMeta(
        "streaming_types",
        "Add LcaStreamToolEvent type + closed-loop fields",
        ("src/store/chat/agents/types/streaming.ts",),
        "low",
        "runtime",
        why="TypeScript types for the LCA tool event protocol",
        technical_detail=(
            "Define LcaStreamToolEvent discriminated union (tool_started/tool_result/"
            "tool_state/run_error). Add lcaClosedLoop and lcaRunError to StreamingResult."
        ),
    ),
    PatchMeta(
        "streaming_handler",
        "Add handleLcaToolEvent() for tool card UI",
        ("src/store/chat/agents/StreamingHandler.ts",),
        "medium",
        "runtime",
        depends_on=("streaming_types",),
        why="Core handler that converts LCA SSE events into tool card UI state",
        technical_detail=(
            "Add handleLcaToolEvent() method: tool_started creates ChatToolPayload cards, "
            "tool_result/tool_state update card content, run_error records errors. "
            "lcaClosedLoop flag prevents client-side tool loop."
        ),
    ),
    PatchMeta(
        "lca_tool_result_merge",
        "Merge LCA tool SSE into ChatToolResult for sandbox cards",
        ("src/store/chat/agents/StreamingHandler.ts",),
        "high",
        "runtime",
        depends_on=("streaming_handler",),
        why="Tool results need structured merge into ChatToolResult shape",
        technical_detail=(
            "Add mergeLcaToolResult() that deep-merges state, extracts stdout from "
            "state.output/state.stdout, and preserves error propagation."
        ),
    ),
    PatchMeta(
        "lca_streaming_types",
        "Extend LcaStreamToolEvent for live stdout + files",
        ("src/store/chat/agents/types/streaming.ts",),
        "low",
        "runtime",
        depends_on=("streaming_types",),
        why="Sandbox tools stream live stdout and produce file artifacts",
        technical_detail="Add content field to tool_state, files[] to tool_result in LcaStreamToolEvent.",
    ),
    PatchMeta(
        "sandbox_generated_files",
        "Show harvested sandbox files on executeCode cards",
        ("packages/builtin-tool-cloud-sandbox/src/client/Render/ExecuteCode/index.tsx",),
        "medium",
        "ui",
        why="Sandbox code execution produces files that should be visible in the UI",
        technical_detail="Add GeneratedFilesStrip component to render file download links from tool state.",
    ),
    PatchMeta(
        "client_transport",
        "Wire onLcaToolEvent callback + error surfacing",
        ("src/store/chat/agents/transports/ClientLLMTransport.ts",),
        "medium",
        "runtime",
        depends_on=("streaming_handler", "chat_callbacks"),
        why="Transport layer must connect SSE events to StreamingHandler",
        technical_detail=(
            "Wire onLcaToolEvent callback in ChatStreamCallbacks to handler.handleChunk. "
            "Surface lcaRunError as transport-level error."
        ),
    ),
    PatchMeta(
        "llm_transport_type",
        "Add lcaClosedLoop to StreamingResult",
        ("packages/agent-runtime/src/transport/llm.ts",),
        "low",
        "runtime",
        why="Type propagation for closed-loop flag through the transport layer",
        technical_detail="Add lcaClosedLoop?: boolean to the StreamingResult type in agent-runtime.",
    ),
    PatchMeta(
        "call_llm_finalizer",
        "Skip client tool loop when lcaClosedLoop",
        ("packages/agent-runtime/src/executors/callLlmFinalizer.ts",),
        "high",
        "runtime",
        depends_on=("llm_transport_type",),
        why="Prevent LobeHub's client-side tool loop from duplicating LCA's server-side execution",
        technical_detail=(
            "Change hasToolsCalling condition: !output.lcaClosedLoop && output.toolsCalling.length > 0. "
            "When LCA handles tools server-side, the client must not re-invoke them."
        ),
    ),
    # ── Provider Routing ────────────────────────────────────────────────
    # LCA uses virtual model names (solo/team/auto) routed through its
    # gateway. These patches ensure LobeHub defaults and routing work.
    PatchMeta(
        "default_model",
        "Set default model/provider to solo/openai",
        (
            "packages/business/const/src/llm.ts",
            "apps/desktop/stubs/business-const/src/index.ts",
        ),
        "low",
        "provider",
        why="LCA's virtual model 'solo' must be the default for new conversations",
        technical_detail=(
            "Replace DEFAULT_MODEL, DEFAULT_PROVIDER, DEFAULT_MINI_MODEL, DEFAULT_MINI_PROVIDER "
            "in both web and desktop const stubs with LCA defaults (solo/openai)."
        ),
    ),
    PatchMeta(
        "openai_guard",
        "LCA virtual models bypass Responses API",
        ("packages/model-runtime/src/providers/openai/index.ts",),
        "medium",
        "provider",
        why="LCA virtual models (solo/team/auto) must use chat/completions, not OpenAI Responses API",
        technical_detail=(
            "Add isLcaGatewayModel check: if model in ['solo','team','auto'], "
            "force chat/completions path regardless of model capabilities."
        ),
    ),
    PatchMeta(
        "provider_order",
        "Move OpenAI provider to first position",
        ("packages/model-bank/src/modelProviders/index.ts",),
        "low",
        "provider",
        why="OpenAI provider (LCA gateway) should be the first/default option",
        technical_detail="Reorder DEFAULT_MODEL_PROVIDER_LIST to put OpenAIProvider first.",
    ),
    # ── Dev Auth ────────────────────────────────────────────────────────
    # Local development without Better Auth. Uses a static dev user to
    # avoid OAuth/login flows during development.
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
        why="Local dev needs no-auth mode; Better Auth requires HTTPS + OAuth",
        technical_detail=(
            "Create 3 new files: localDevNoAuth.ts (flag check), "
            "LocalDevAuth/index.tsx (wrapper), LocalDevUserUpdater.tsx (injects static user)."
        ),
    ),
    PatchMeta(
        "dev_auth_vite",
        "Swap BetterAuth for LocalDevAuth in Vite mode",
        ("src/layout/AuthProvider/index.vite.tsx",),
        "medium",
        "auth",
        depends_on=("dev_auth_files",),
        why="Vite SPA mode needs the auth provider swap",
        technical_detail="When ENABLE_MOCK_DEV_USER is set, render LocalDevAuth instead of BetterAuth.",
    ),
    PatchMeta(
        "middleware_mock_user",
        "Skip Better Auth session gate for dev",
        ("src/libs/next/proxy/define-config.ts",),
        "medium",
        "auth",
        why="Next.js middleware blocks unauthenticated requests; dev mode must bypass",
        technical_detail="Early-return from middleware when ENABLE_MOCK_DEV_USER flag is set.",
    ),
    # ── Route Adaptation ────────────────────────────────────────────────
    # LCA's single-agent UI has different routing semantics than LobeHub's
    # multi-agent marketplace. These patches stabilize topic/conversation IDs.
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
        why="LCA needs stable topicId from URL; LobeHub's default resolution is fragile",
        technical_detail=(
            "Add resolveAgentChatRouteTopicId() that prefers route params over pathname parsing. "
            "Update useChatRouteSync and AgentIdSync to use it."
        ),
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
        depends_on=("dev_auth_files",),
        why="Market fork requires OIDC which needs HTTPS; local dev is HTTP",
        technical_detail="Check isLocalDevNoAuth() and skip OIDC redirect, directly fork to local agent.",
    ),
    # ── Dev UX ──────────────────────────────────────────────────────────
    PatchMeta(
        "lan_dev",
        "Use VITE_DEV_HOST for Vite dev asset URLs",
        ("src/libs/spaHtml/index.ts",),
        "low",
        "devux",
        why="Developers need LAN access from mobile devices; hardcoded localhost prevents this",
        technical_detail="Replace hardcoded 'localhost' with process.env.VITE_DEV_HOST in resolveCiteDevOrigin.",
    ),
    PatchMeta(
        "turbopack_dev",
        "Enable Turbopack for faster dev compilation",
        ("scripts/devStartupSequence.mts",),
        "low",
        "devux",
        why="Turbopack significantly speeds up Next.js dev builds",
        technical_detail="Add '--turbo' flag to the next dev command in devStartupSequence.",
    ),
    # ── File Proxy ──────────────────────────────────────────────────────
    PatchMeta(
        "file_proxy_rewrite",
        "Proxy /files/* to LCA gateway for artifact downloads",
        ("next.config.ts",),
        "low",
        "proxy",
        why="LCA tool artifacts are served by the gateway, not LobeHub's file system",
        technical_detail="Add Next.js rewrite rule: /files/* → LCA gateway /files/* endpoint.",
    ),
    # ── Reasoning (per-step thinking blocks) ────────────────────────────
    # LCA agents think in multiple steps. Each LLM call produces a separate
    # reasoning section. These patches enable per-step collapsible UI blocks
    # instead of merging all thinking into one block.
    PatchMeta(
        "reasoning_segmentation",
        "Per-step reasoning blocks via reasoning_start/end events",
        (
            "src/store/chat/agents/types/streaming.ts",
            "src/store/chat/agents/StreamingHandler.ts",
        ),
        "medium",
        "runtime",
        why="LCA emits reasoning_start/end per LLM call; frontend must track boundaries",
        technical_detail=(
            "Add reasoning_start/reasoning_end to LcaStreamToolEvent union. "
            "Handle in handleLcaToolEvent by calling endReasoningIfNeeded()."
        ),
    ),
    PatchMeta(
        "tool_result_files",
        "Pass files[] from tool_result into card state for rendering",
        ("src/store/chat/agents/StreamingHandler.ts",),
        "low",
        "runtime",
        depends_on=("lca_tool_result_merge",),
        why="Tool results may include generated files that need UI rendering",
        technical_detail="Spread event.files into merged tool state when tool_result includes files[].",
    ),
    PatchMeta(
        "reasoning_section_type",
        "Add reasoning_section type to LcaStreamToolEvent union",
        ("src/store/chat/agents/types/streaming.ts",),
        "low",
        "runtime",
        depends_on=("reasoning_segmentation",),
        why="Backend emits reasoning_section events with complete thinking text per turn",
        technical_detail="Add { content: string; step: number; type: 'reasoning_section' } to union.",
    ),
    PatchMeta(
        "reasoning_section_handler",
        "Multi-section reasoning state: completedReasoningSections + 7 call sites",
        ("src/store/chat/agents/StreamingHandler.ts",),
        "high",
        "runtime",
        depends_on=("reasoning_section_type", "streaming_handler"),
        why="Each LLM turn's thinking must be saved as a separate section for individual rendering",
        technical_detail=(
            "Add completedReasoningSections[] array. On reasoning_section event: save content, "
            "add to reasoningParts, reset thinkingContent. Update getThinkingContent(), "
            "handleReasoningChunk(), notifyContentPartUpdate(), buildReasoningState(), "
            "and buildFinalResult() to handle multi-section state."
        ),
    ),
    PatchMeta(
        "reasoning_multi_block",
        "Render multiple <Thinking> Accordions for per-step reasoning sections",
        ("src/features/Conversation/Messages/components/Reasoning.tsx",),
        "medium",
        "ui",
        depends_on=("reasoning_section_handler",),
        why="Upstream renders all reasoning in one block; LCA needs one block per LLM turn",
        technical_detail=(
            "When tempDisplayContent has multiple text parts, render each as a separate "
            "<Thinking> Accordion. Only the last block shows the 'thinking' spinner. "
            "Falls back to single-block rendering for non-LCA messages."
        ),
    ),
    # ── Misc ────────────────────────────────────────────────────────────
    PatchMeta(
        "topic_route_test",
        "Add test for resolveAgentChatRouteTopicId",
        ("src/features/AgentSidebar/utils/agentPathname.test.ts",),
        "low",
        "route",
        depends_on=("topic_route",),
        why="Test coverage for the new routing function added by topic_route patch",
        technical_detail="Add test cases for resolveAgentChatRouteTopicId with params, pathname, and edge cases.",
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
    "lca_tool_result_merge": p_lca_tool_result_merge,
    "lca_streaming_types": p_lca_streaming_types,
    "sandbox_generated_files": p_sandbox_generated_files,
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
    "turbopack_dev": p_turbopack_dev,
    "file_proxy_rewrite": p_file_proxy_rewrite,
    "reasoning_segmentation": p_reasoning_segmentation,
    "tool_result_files": p_tool_result_files,
    "reasoning_section_type": p_reasoning_section_type,
    "reasoning_section_handler": p_reasoning_section_handler,
    "reasoning_multi_block": p_reasoning_multi_block,
    "topic_route_test": p_topic_route_test,
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
    "lca_tool_result_merge": ("src/store/chat/agents/StreamingHandler.ts", "mergeLcaToolResult"),
    "lca_streaming_types": ("src/store/chat/agents/types/streaming.ts", "tool_state_content"),
    "sandbox_generated_files": (
        "packages/builtin-tool-cloud-sandbox/src/client/Render/ExecuteCode/index.tsx",
        "GeneratedFilesStrip",
    ),
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
    "turbopack_dev": (
        "scripts/devStartupSequence.mts",
        "'--turbo'",
    ),
    "file_proxy_rewrite": ("next.config.ts", "LCA: file proxy"),
    "reasoning_segmentation": (
        "src/store/chat/agents/StreamingHandler.ts",
        "'reasoning_start'",
    ),
    "tool_result_files": (
        "src/store/chat/agents/StreamingHandler.ts",
        "event.files",
    ),
    "reasoning_section_type": (
        "src/store/chat/agents/types/streaming.ts",
        "reasoning_section",
    ),
    "reasoning_section_handler": (
        "src/store/chat/agents/StreamingHandler.ts",
        "completedReasoningSections",
    ),
    "reasoning_multi_block": (
        "src/features/Conversation/Messages/components/Reasoning.tsx",
        "LCA: multi-block reasoning",
    ),
    "topic_route_test": (
        "src/features/AgentSidebar/utils/agentPathname.test.ts",
        "resolveAgentChatRouteTopicId",
    ),
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


def list_patches(*, verbose: bool = False) -> None:
    print(f"{'#':>2}  {'Name':<28} {'Risk':<6} {'Category':<10} Description")
    print("─" * 100)
    for i, meta in enumerate(PATCHES, 1):
        deps = f" ← {','.join(meta.depends_on)}" if meta.depends_on else ""
        print(
            f"{i:>2}  {meta.name:<28} {meta.risk:<6} {meta.category:<10} {meta.description}{deps}"
        )
        if verbose and meta.why:
            print(f"     why: {meta.why}")
        if verbose and meta.technical_detail:
            print(f"     how: {meta.technical_detail}")
    print(f"\nTotal: {len(PATCHES)} patches across {len({m.category for m in PATCHES})} categories")
    print(f"Upstream: LobeHub {_read_origin_release()}")
    print("Commands: apply | verify | list [--verbose] | drift | manifest | doctor")


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
#  DRIFT GUARD — detect unregistered source modifications
# =======================================================================

_UPSTREAM = ROOT / ".lobehub-upstream"

# Files/dirs that are expected to differ and are NOT patches
_DRIFT_IGNORE = frozenset(
    {
        ".env",
        ".lca-patched",
        ".lca-integration-patched",
        ".lca-qwen-defaults-patched",
        ".lca-origin.json",
        ".agent-tracing",
        ".llm-generation-tracing",
        "next-env.d.ts",
    }
)

_DRIFT_IGNORE_PREFIXES = (
    "node_modules/",
    ".next/",
    ".turbo/",
    "dist/",
    "coverage/",
    ".git/",
    "public/_spa/",
    "public/_spa-auth/",
    ".pytest_cache/",
    "docker-compose/dev/data/",
)


def _collect_patch_covered_files() -> set[str]:
    """Build the set of all file paths that registered patches touch."""
    covered: set[str] = set()
    for meta in PATCHES:
        covered.update(meta.files)
    return covered


def _is_ignored(rel: str) -> bool:
    if rel in _DRIFT_IGNORE:
        return True
    if any(rel.startswith(p) for p in _DRIFT_IGNORE_PREFIXES):
        return True
    # Also ignore nested node_modules anywhere in the path
    return "/node_modules/" in rel or rel.endswith("/node_modules")


def drift_guard(*, verbose: bool = False) -> list[str]:
    """Compare upstream vs lobehub-ui and report unregistered modifications.

    Returns a list of violation messages. Empty list = clean.
    """
    if not _UPSTREAM.is_dir():
        return [f"upstream cache not found: {_UPSTREAM}"]
    if not UI.is_dir():
        return [f"lobehub-ui/ not found: {UI}"]

    covered = _collect_patch_covered_files()
    violations: list[str] = []

    # Walk lobehub-ui and compare against upstream
    for path in UI.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(UI))
        if _is_ignored(rel):
            continue

        upstream_path = _UPSTREAM / rel
        if not upstream_path.is_file():
            # New file — must be created by a patch
            if rel not in covered:
                violations.append(f"NEW FILE (not in any patch): {rel}")
            continue

        # Existing file — check if content differs
        try:
            if path.read_bytes() == upstream_path.read_bytes():
                continue
        except OSError:
            continue

        # File differs — must be covered by a patch
        if rel not in covered:
            violations.append(f"MODIFIED (not in any patch): {rel}")

    if verbose:
        if violations:
            print(f"\n[drift] ❌ {len(violations)} unregistered modification(s):")
            for v in violations:
                print(f"  • {v}")
            print("\n[drift] FIX: register these changes as patches in patch_lobehub.py")
            print("[drift] Then run: python3 deploy/lobehub/patch_lobehub.py --reset")
        else:
            print("[drift] ✅ all modifications covered by registered patches")

    return violations


def generate_manifest() -> dict:
    """Generate a structured JSON manifest of all patches."""
    patches = []
    for i, meta in enumerate(PATCHES, 1):
        marker_info = _VERIFY_MARKERS.get(meta.name)
        patches.append(
            {
                "index": i,
                "name": meta.name,
                "description": meta.description,
                "category": meta.category,
                "risk": meta.risk,
                "files": list(meta.files),
                "depends_on": list(meta.depends_on),
                "why": meta.why,
                "technical_detail": meta.technical_detail,
                "verify_marker": marker_info[1] if marker_info else None,
            }
        )
    return {
        "schema_version": 1,
        "upstream_release": _read_origin_release(),
        "total_patches": len(PATCHES),
        "categories": sorted({m.category for m in PATCHES}),
        "patches": patches,
    }


def doctor() -> int:
    """Run all health checks: verify + drift + consistency."""
    print("=" * 60)
    print("  LobeHub Patch Doctor")
    print("=" * 60)

    issues = 0

    # 1. Verify all patch markers
    print("\n── 1. Patch markers ──")
    verify_results = verify_patches()
    broken = [r for r in verify_results if r.status == "broken"]
    issues += len(broken)

    # 2. Drift guard
    print("\n── 2. Drift guard ──")
    drift_violations = drift_guard(verbose=True)
    issues += len(drift_violations)

    # 3. Consistency: every patch in PATCHES has a func and marker
    print("\n── 3. Registry consistency ──")
    for meta in PATCHES:
        if meta.name not in _PATCH_FUNCS:
            print(f"  ❌ {meta.name}: missing in _PATCH_FUNCS")
            issues += 1
        if meta.name not in _VERIFY_MARKERS:
            print(f"  ⚠️  {meta.name}: no verify marker (optional)")

    # 4. Dependency check
    print("\n── 4. Dependency graph ──")
    all_names = {m.name for m in PATCHES}
    for meta in PATCHES:
        for dep in meta.depends_on:
            if dep not in all_names:
                print(f"  ❌ {meta.name}: depends on unknown patch '{dep}'")
                issues += 1

    # Summary
    print("\n" + "=" * 60)
    if issues == 0:
        print("  ✅ All checks passed")
    else:
        print(f"  ❌ {issues} issue(s) found")
    print("=" * 60)
    return issues


# =======================================================================
#  CLI
# =======================================================================

_COMMANDS = ("apply", "verify", "list", "drift", "manifest", "doctor")


def main() -> None:
    args = sys.argv[1:]
    cmd = "apply"
    names: list[str] = []
    reset = False
    verbose = False

    i = 0
    while i < len(args):
        a = args[i]
        if a in _COMMANDS:
            cmd = a
        elif a == "--reset":
            reset = True
        elif a in ("--verbose", "-v"):
            verbose = True
        elif a in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            names.append(a)
        i += 1

    if cmd == "list":
        list_patches(verbose=verbose)
    elif cmd == "verify":
        results = verify_patches(tuple(names))
        broken = [r for r in results if r.status == "broken"]
        sys.exit(1 if broken else 0)
    elif cmd == "drift":
        violations = drift_guard(verbose=True)
        sys.exit(1 if violations else 0)
    elif cmd == "manifest":
        manifest = generate_manifest()
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    elif cmd == "doctor":
        issues = doctor()
        sys.exit(1 if issues else 0)
    else:
        results = apply_patches(tuple(names), reset=reset)
        broken = [r for r in results if r.status == "broken"]
        sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
