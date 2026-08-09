# Message-Based Turn Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ChatProjector + TurnTimelineProjector with MessageProjector that projects journal events into Message[], achieving LobeHub-style message flow rendering.

**Architecture:** Hybrid Turn + Message model — Turn remains the top-level container (one per user question), but internally projects to Message[] instead of process[] + finalAnswer. Each message is an independent UI element with explicit kind (thinking / tool_call / answer / etc.), sorted by completion time. Existing rendering components (ThinkingPanel, ToolCallCard, WorkflowCollapse) are reused via adapter functions that map Message → Block interfaces.

**Tech Stack:** TypeScript, React, Vitest, Testing Library, existing journal event types

## Global Constraints

- Delete `normalizeChatMarkdown()` entirely — trust LLM markdown output
- Reuse existing `ThinkingPanel` / `ToolCallCard` / `WorkflowCollapse` / `SandboxPanel` components via adapter functions
- Message sorting: completed messages by `completedAt` ascending, running messages by `startedAt` at end
- Feature flag `message-renderer` controls new/old rendering switch during Phase 2
- All new code must have unit tests (Vitest) with >80% coverage
- Commit after each task with conventional commit message

---

## Task 1: Define Message Type System

**Files:**
- Create: `web/src/projectors/message-types.ts`
- Test: `web/src/projectors/__tests__/message-types.test.ts`

**Interfaces:**
- Produces: `Message`, `MessageKind`, `MessageMetadata`, `Turn` types used by all subsequent tasks

- [ ] **Step 1: Write type definition tests**

```typescript
// web/src/projectors/__tests__/message-types.test.ts
import { describe, it, expect } from "vitest";
import type { Message, MessageKind, Turn } from "../message-types";

describe("Message types", () => {
  it("should define all message kinds", () => {
    const kinds: MessageKind[] = [
      "casting",
      "thinking",
      "tool_call",
      "sandbox",
      "delegation",
      "synthesis",
      "answer",
      "error",
      "insight",
    ];
    expect(kinds).toHaveLength(9);
  });

  it("should create a valid thinking message", () => {
    const msg: Message = {
      id: "thinking:run1:historian",
      kind: "thinking",
      agentRole: "historian",
      content: "分析历史背景...",
      streaming: true,
      status: "running",
      startedAt: Date.now(),
      metadata: { durationMs: undefined },
    };
    expect(msg.kind).toBe("thinking");
    expect(msg.streaming).toBe(true);
  });

  it("should create a valid tool_call message", () => {
    const msg: Message = {
      id: "tool:inv123",
      kind: "tool_call",
      content: "",
      streaming: false,
      status: "done",
      startedAt: Date.now() - 1000,
      completedAt: Date.now(),
      metadata: {
        toolName: "search_knowledge",
        argumentsPreview: '{"query": "test"}',
        resultPreview: '{"results": []}',
        latencyMs: 500,
        ok: true,
      },
    };
    expect(msg.metadata?.toolName).toBe("search_knowledge");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- message-types.test.ts`
Expected: FAIL — `message-types.ts` does not exist

- [ ] **Step 3: Implement Message types**

```typescript
// web/src/projectors/message-types.ts
export type MessageKind =
  | "casting"
  | "thinking"
  | "tool_call"
  | "sandbox"
  | "delegation"
  | "synthesis"
  | "answer"
  | "error"
  | "insight";

export interface MessageMetadata {
  readonly toolName?: string;
  readonly argumentsPreview?: string;
  readonly resultPreview?: string;
  readonly latencyMs?: number;
  readonly ok?: boolean;
  readonly error?: string;
  readonly invocationId?: string;
  readonly durationMs?: number;
  readonly governanceKind?: string;
  readonly leadRole?: string;
  readonly selectedRoles?: readonly string[];
  readonly rationale?: string;
  readonly objectivePreview?: string;
  readonly calleeRole?: string;
  readonly subtaskPreview?: string;
  readonly delegationId?: string;
  readonly fromRole?: string;
  readonly stdout?: string;
  readonly stderr?: string;
  readonly sealed?: boolean;
  readonly errorMessage?: string;
  readonly insightKind?: string;
  readonly summary?: string;
  readonly detail?: string;
  readonly method?: string;
  readonly candidateCount?: number;
}

export interface Message {
  readonly id: string;
  readonly kind: MessageKind;
  readonly agentRole?: string;
  readonly content: string;
  readonly streaming: boolean;
  readonly status: "running" | "done" | "error";
  readonly startedAt: number;
  readonly completedAt?: number;
  readonly metadata?: MessageMetadata;
}

export interface Turn {
  readonly id: string;
  readonly runId: string;
  readonly question: string;
  readonly mode: "solo" | "team";
  readonly messages: readonly Message[];
  readonly status: "running" | "completed" | "failed";
  readonly startedAt: number;
  readonly completedAt?: number;
  readonly teamId?: string;
  readonly errorMessage?: string;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- message-types.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/projectors/message-types.ts web/src/projectors/__tests__/message-types.test.ts
git commit -m "feat(projector): define Message and Turn type system

Introduce MessageKind union (9 types) and Message/Turn interfaces
for message-based turn projection (ADR-0053)."
```

---

## Task 2: Implement Message Sorting Logic

**Files:**
- Create: `web/src/projectors/message-sort.ts`
- Test: `web/src/projectors/__tests__/message-sort.test.ts`

**Interfaces:**
- Consumes: `Message` from Task 1
- Produces: `sortMessages(messages: readonly Message[]): readonly Message[]`

- [ ] **Step 1: Write sorting tests**

```typescript
// web/src/projectors/__tests__/message-sort.test.ts
import { describe, it, expect } from "vitest";
import { sortMessages } from "../message-sort";
import type { Message } from "../message-types";

function makeMessage(overrides: Partial<Message>): Message {
  return {
    id: "msg",
    kind: "answer",
    content: "",
    streaming: false,
    status: "done",
    startedAt: 0,
    ...overrides,
  };
}

describe("sortMessages", () => {
  it("should sort completed messages by completedAt ascending", () => {
    const msgs = [
      makeMessage({ id: "a", completedAt: 300 }),
      makeMessage({ id: "b", completedAt: 100 }),
      makeMessage({ id: "c", completedAt: 200 }),
    ];
    const sorted = sortMessages(msgs);
    expect(sorted.map((m) => m.id)).toEqual(["b", "c", "a"]);
  });

  it("should place running messages after completed ones", () => {
    const msgs = [
      makeMessage({ id: "running", status: "running", startedAt: 50 }),
      makeMessage({ id: "done", completedAt: 100 }),
    ];
    const sorted = sortMessages(msgs);
    expect(sorted.map((m) => m.id)).toEqual(["done", "running"]);
  });

  it("should sort running messages by startedAt ascending", () => {
    const msgs = [
      makeMessage({ id: "r2", status: "running", startedAt: 200 }),
      makeMessage({ id: "r1", status: "running", startedAt: 100 }),
    ];
    const sorted = sortMessages(msgs);
    expect(sorted.map((m) => m.id)).toEqual(["r1", "r2"]);
  });

  it("should handle mixed completed and running", () => {
    const msgs = [
      makeMessage({ id: "r1", status: "running", startedAt: 300 }),
      makeMessage({ id: "d1", completedAt: 200 }),
      makeMessage({ id: "r2", status: "running", startedAt: 250 }),
      makeMessage({ id: "d2", completedAt: 100 }),
    ];
    const sorted = sortMessages(msgs);
    expect(sorted.map((m) => m.id)).toEqual(["d2", "d1", "r2", "r1"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- message-sort.test.ts`
Expected: FAIL — `message-sort.ts` does not exist

- [ ] **Step 3: Implement sorting logic**

```typescript
// web/src/projectors/message-sort.ts
import type { Message } from "./message-types";

export function sortMessages(messages: readonly Message[]): readonly Message[] {
  return [...messages].sort((a, b) => {
    const aRunning = a.status === "running" ? 1 : 0;
    const bRunning = b.status === "running" ? 1 : 0;
    if (aRunning !== bRunning) return aRunning - bRunning;

    if (a.completedAt != null && b.completedAt != null) {
      return a.completedAt - b.completedAt;
    }

    return a.startedAt - b.startedAt;
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- message-sort.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/projectors/message-sort.ts web/src/projectors/__tests__/message-sort.test.ts
git commit -m "feat(projector): implement message sorting logic

Sort completed messages by completedAt ascending, running messages
by startedAt at end. Ensures causal ordering in UI."
```

---

## Task 3: Implement MessageProjector Core

**Files:**
- Create: `web/src/projectors/message-projector.ts`
- Test: `web/src/projectors/__tests__/message-projector.test.ts`

**Interfaces:**
- Consumes: `Message`, `Turn` from Task 1; `sortMessages` from Task 2; `StampedEvent` from existing contracts
- Produces: `MessageProjector` class with `start()`, `onEvent()`, `snapshot()`

- [ ] **Step 1: Write projector tests for thinking messages**

```typescript
// web/src/projectors/__tests__/message-projector.test.ts
import { describe, it, expect } from "vitest";
import { MessageProjector } from "../message-projector";
import type { StampedEvent } from "../../contracts/stamped";
import type { ReasoningDelta, ReasoningCompleted } from "../../contracts";

function makeStamped(event: any, ts = Date.now(), runId = "run1", role = "historian"): StampedEvent {
  return { event, ts, scope: { run_id: runId, agent_role: role } };
}

describe("MessageProjector", () => {
  it("should create thinking message from ReasoningDelta", () => {
    const projector = new MessageProjector();
    projector.start("测试问题", "solo");

    const delta: ReasoningDelta = {
      type: "ReasoningDelta",
      step: 1,
      text_delta: "分析中...",
      seq: 1,
    };
    const turn = projector.onEvent(makeStamped(delta, 1000));

    expect(turn.messages).toHaveLength(1);
    expect(turn.messages[0].kind).toBe("thinking");
    expect(turn.messages[0].content).toBe("分析中...");
    expect(turn.messages[0].streaming).toBe(true);
  });

  it("should append multiple ReasoningDelta to same thinking message", () => {
    const projector = new MessageProjector();
    projector.start("测试", "solo");

    projector.onEvent(makeStamped({ type: "ReasoningDelta", step: 1, text_delta: "第一句", seq: 1 }, 1000));
    projector.onEvent(makeStamped({ type: "ReasoningDelta", step: 1, text_delta: "第二句", seq: 2 }, 1001));

    const turn = projector.snapshot();
    expect(turn.messages).toHaveLength(1);
    expect(turn.messages[0].content).toBe("第一句第二句");
  });

  it("should mark thinking message done on ReasoningCompleted", () => {
    const projector = new MessageProjector();
    projector.start("测试", "solo");

    projector.onEvent(makeStamped({ type: "ReasoningDelta", step: 1, text_delta: "思考", seq: 1 }, 1000));
    const turn = projector.onEvent(
      makeStamped({ type: "ReasoningCompleted", step: 1, duration_ms: 500, content_preview: "" }, 1500)
    );

    expect(turn.messages[0].streaming).toBe(false);
    expect(turn.messages[0].status).toBe("done");
    expect(turn.messages[0].completedAt).toBe(1500);
    expect(turn.messages[0].metadata?.durationMs).toBe(500);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- message-projector.test.ts`
Expected: FAIL — `MessageProjector` does not exist

- [ ] **Step 3: Implement MessageProjector (thinking events only)**

```typescript
// web/src/projectors/message-projector.ts
import type { StampedEvent } from "../contracts/stamped";
import type { Message, Turn } from "./message-types";
import { sortMessages } from "./message-sort";

interface InternalMessage extends Message {
  buffer: string;
}

export class MessageProjector {
  private turn: Turn | null = null;
  private messages = new Map<string, InternalMessage>();

  start(question: string, mode: "solo" | "team"): void {
    this.turn = {
      id: `turn-${Date.now()}`,
      runId: "",
      question,
      mode,
      messages: [],
      status: "running",
      startedAt: Date.now(),
    };
    this.messages.clear();
  }

  onEvent(stamped: StampedEvent): Turn {
    const e = stamped.event;
    const ts = stamped.ts;
    const runId = stamped.scope.run_id;
    const role = stamped.scope.agent_role;

    if (this.turn && !this.turn.runId) {
      this.turn = { ...this.turn, runId };
    }

    switch (e.type) {
      case "ReasoningDelta": {
        const key = `thinking:${runId}:${role}`;
        const msg = this.messages.get(key) ?? this.createThinkingMessage(key, role, ts);
        msg.buffer += e.text_delta;
        msg.content = msg.buffer;
        msg.streaming = true;
        this.messages.set(key, msg);
        break;
      }
      case "ReasoningCompleted": {
        const key = `thinking:${runId}:${role}`;
        const msg = this.messages.get(key);
        if (msg) {
          msg.streaming = false;
          msg.status = "done";
          msg.completedAt = ts;
          msg.metadata = { ...msg.metadata, durationMs: e.duration_ms };
        }
        break;
      }
    }

    return this.buildTurn();
  }

  snapshot(): Turn {
    return this.buildTurn();
  }

  private createThinkingMessage(id: string, agentRole: string, ts: number): InternalMessage {
    return {
      id,
      kind: "thinking",
      agentRole,
      content: "",
      buffer: "",
      streaming: false,
      status: "running",
      startedAt: ts,
      metadata: {},
    };
  }

  private buildTurn(): Turn {
    if (!this.turn) {
      throw new Error("MessageProjector not started");
    }
    const sorted = sortMessages(Array.from(this.messages.values()));
    return { ...this.turn, messages: sorted };
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- message-projector.test.ts`
Expected: PASS

- [ ] **Step 5: Add tests for tool_call events**

Add to `message-projector.test.ts`:

```typescript
it("should create tool_call message from ToolStarted", () => {
  const projector = new MessageProjector();
  projector.start("测试", "solo");

  const turn = projector.onEvent(
    makeStamped({
      type: "ToolStarted",
      tool_name: "search",
      arguments_preview: '{"q": "test"}',
      invocation_id: "inv1",
    }, 1000)
  );

  expect(turn.messages).toHaveLength(1);
  expect(turn.messages[0].kind).toBe("tool_call");
  expect(turn.messages[0].status).toBe("running");
  expect(turn.messages[0].metadata?.toolName).toBe("search");
});

it("should update tool_call message on ToolInvoked", () => {
  const projector = new MessageProjector();
  projector.start("测试", "solo");

  projector.onEvent(makeStamped({
    type: "ToolStarted",
    tool_name: "search",
    arguments_preview: "",
    invocation_id: "inv1",
  }, 1000));

  const turn = projector.onEvent(makeStamped({
    type: "ToolInvoked",
    tool_name: "search",
    result_preview: '{"results": []}',
    ok: true,
    latency_ms: 500,
    invocation_id: "inv1",
  }, 1500));

  expect(turn.messages[0].status).toBe("done");
  expect(turn.messages[0].completedAt).toBe(1500);
  expect(turn.messages[0].metadata?.latencyMs).toBe(500);
});
```

- [ ] **Step 6: Implement tool_call event handling**

Add to `MessageProjector.onEvent()` switch:

```typescript
case "ToolStarted": {
  const key = `tool:${e.invocation_id || `unknown-${ts}`}`;
  const msg: InternalMessage = {
    id: key,
    kind: "tool_call",
    content: "",
    buffer: "",
    streaming: false,
    status: "running",
    startedAt: ts,
    metadata: {
      toolName: e.tool_name,
      argumentsPreview: e.arguments_preview,
      invocationId: e.invocation_id,
    },
  };
  this.messages.set(key, msg);
  break;
}
case "ToolInvoked": {
  const key = `tool:${e.invocation_id || `unknown-${ts}`}`;
  const msg = this.messages.get(key);
  if (msg) {
    msg.status = e.ok ? "done" : "error";
    msg.completedAt = ts;
    msg.metadata = {
      ...msg.metadata,
      resultPreview: e.result_preview,
      latencyMs: e.latency_ms,
      ok: e.ok,
      error: e.error,
    };
  }
  break;
}
```

- [ ] **Step 7: Run all projector tests**

Run: `cd web && npm test -- message-projector.test.ts`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add web/src/projectors/message-projector.ts web/src/projectors/__tests__/message-projector.test.ts
git commit -m "feat(projector): implement MessageProjector core

Project ReasoningDelta/Completed → thinking messages,
ToolStarted/Invoked → tool_call messages. Message-based
projection for LobeHub-style rendering (ADR-0053)."
```

---

## Task 4: Implement Block Adapter Functions

**Files:**
- Create: `web/src/components/thread/message-block-adapters.ts`
- Test: `web/src/components/thread/__tests__/message-block-adapters.test.ts`

**Interfaces:**
- Consumes: `Message` from Task 1
- Produces: `toThinkingBlock()`, `toToolBlock()`, `toSandboxBlock()` adapter functions

- [ ] **Step 1: Write adapter tests**

```typescript
// web/src/components/thread/__tests__/message-block-adapters.test.ts
import { describe, it, expect } from "vitest";
import { toThinkingBlock, toToolBlock } from "../message-block-adapters";
import type { Message } from "../../../projectors/message-types";

describe("toThinkingBlock", () => {
  it("should convert thinking message to ThinkingBlock", () => {
    const msg: Message = {
      id: "thinking:run1:historian",
      kind: "thinking",
      agentRole: "historian",
      content: "分析中...",
      streaming: true,
      status: "running",
      startedAt: 1000,
      metadata: { durationMs: undefined },
    };
    const block = toThinkingBlock(msg);
    expect(block.kind).toBe("thinking");
    expect(block.id).toBe("thinking:run1:historian");
    expect(block.status).toBe("running");
    expect(block.content).toBe("分析中...");
  });
});

describe("toToolBlock", () => {
  it("should convert tool_call message to ToolBlock", () => {
    const msg: Message = {
      id: "tool:inv1",
      kind: "tool_call",
      content: "",
      streaming: false,
      status: "done",
      startedAt: 1000,
      completedAt: 1500,
      metadata: {
        toolName: "search",
        argumentsPreview: '{"q": "test"}',
        resultPreview: '{"results": []}',
        latencyMs: 500,
        ok: true,
        invocationId: "inv1",
      },
    };
    const block = toToolBlock(msg);
    expect(block.kind).toBe("tool");
    expect(block.toolName).toBe("search");
    expect(block.status).toBe("done");
    expect(block.latencyMs).toBe(500);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm test -- message-block-adapters.test.ts`
Expected: FAIL

- [ ] **Step 3: Implement adapters**

```typescript
// web/src/components/thread/message-block-adapters.ts
import type { Message } from "../../projectors/message-types";
import type { ThinkingBlock, ToolBlock, SandboxBlock } from "../../projectors/types";

export function toThinkingBlock(msg: Message): ThinkingBlock {
  return {
    kind: "thinking",
    id: msg.id,
    status: msg.streaming ? "running" : "done",
    content: msg.content,
    durationMs: msg.metadata?.durationMs,
  };
}

export function toToolBlock(msg: Message): ToolBlock {
  return {
    kind: "tool",
    id: msg.id,
    status: msg.status === "running" ? "running" : msg.status === "error" ? "error" : "done",
    toolName: msg.metadata?.toolName || "",
    argumentsPreview: msg.metadata?.argumentsPreview || "",
    resultPreview: msg.metadata?.resultPreview || "",
    ok: msg.metadata?.ok,
    latencyMs: msg.metadata?.latencyMs,
    error: msg.metadata?.error,
    invocationId: msg.metadata?.invocationId || "",
    agentRole: msg.agentRole,
  };
}

export function toSandboxBlock(msg: Message): SandboxBlock {
  return {
    kind: "sandbox",
    id: msg.id,
    status: msg.metadata?.sealed ? "done" : "running",
    invocationId: msg.metadata?.invocationId || "",
    stdout: msg.metadata?.stdout || "",
    stderr: msg.metadata?.stderr || "",
    sealed: msg.metadata?.sealed || false,
    agentRole: msg.agentRole,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm test -- message-block-adapters.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/components/thread/message-block-adapters.ts web/src/components/thread/__tests__/message-block-adapters.test.ts
git commit -m "feat(ui): add Message → Block adapter functions

Enable reuse of existing ThinkingPanel/ToolCallCard/SandboxPanel
by adapting Message interface to Block interface."
```

---

## Task 5: Implement MessageRenderer Component

**Files:**
- Create: `web/src/components/thread/MessageRenderer.tsx`

**Interfaces:**
- Consumes: `Message` from Task 1; adapter functions from Task 4; existing `ThinkingPanel`, `ToolCallCard`, `SandboxPanel`

- [ ] **Step 1: Implement MessageRenderer**

```typescript
// web/src/components/thread/MessageRenderer.tsx
import type { Message } from "../../projectors/message-types";
import { ThinkingPanel } from "../turn/ThinkingPanel";
import { ToolCallCard } from "../turn/ToolCallCard";
import { SandboxPanel } from "../turn/SandboxPanel";
import { toThinkingBlock, toToolBlock, toSandboxBlock } from "./message-block-adapters";

export function MessageRenderer({ message }: { message: Message }) {
  switch (message.kind) {
    case "thinking":
      return <ThinkingPanel block={toThinkingBlock(message)} />;
    case "tool_call":
      return <ToolCallCard block={toToolBlock(message)} />;
    case "sandbox":
      return <SandboxPanel block={toSandboxBlock(message)} />;
    case "answer":
      return <div className="lobe-answer-block">{message.content}</div>;
    default:
      return <div>TODO: {message.kind}</div>;
  }
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd web && npm run build`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add web/src/components/thread/MessageRenderer.tsx
git commit -m "feat(ui): implement MessageRenderer component

Dispatch Message to appropriate renderer (ThinkingPanel,
ToolCallCard, SandboxPanel) via adapter functions."
```

---

## Task 6: Implement MessageList Component

**Files:**
- Create: `web/src/components/thread/MessageList.tsx`

**Interfaces:**
- Consumes: `Turn` from Task 1; `MessageRenderer` from Task 5; existing `ProcessFold`

- [ ] **Step 1: Implement MessageList**

```typescript
// web/src/components/thread/MessageList.tsx
import type { Turn } from "../../projectors/message-types";
import { MessageRenderer } from "./MessageRenderer";
import { ProcessFold } from "../turn/ProcessFold";
import { formatProcessDuration } from "../../lib/format-duration";

export function MessageList({ turn }: { turn: Turn }) {
  const processMessages = turn.messages.filter(
    (m) => m.kind !== "answer" && m.kind !== "insight"
  );
  const answerMessages = turn.messages.filter((m) => m.kind === "answer");
  const insightMessages = turn.messages.filter((m) => m.kind === "insight");
  const isDone = turn.status !== "running";

  const totalDurationMs = turn.completedAt
    ? turn.completedAt - turn.startedAt
    : undefined;
  const durationText = totalDurationMs
    ? formatProcessDuration(totalDurationMs)
    : undefined;

  return (
    <div className="grid gap-2.5">
      {processMessages.length > 0 && isDone ? (
        <ProcessFold
          stepCount={processMessages.length}
          durationText={durationText}
        >
          {processMessages.map((m) => (
            <MessageRenderer key={m.id} message={m} />
          ))}
        </ProcessFold>
      ) : (
        processMessages.map((m) => <MessageRenderer key={m.id} message={m} />)
      )}

      {answerMessages.map((m) => (
        <MessageRenderer key={m.id} message={m} />
      ))}

      {insightMessages.map((m) => (
        <MessageRenderer key={m.id} message={m} />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd web && npm run build`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add web/src/components/thread/MessageList.tsx
git commit -m "feat(ui): implement MessageList component

Render process messages in ProcessFold when done, inline when running.
Answer messages always outside ProcessFold."
```

---

## Task 7: Remove normalizeChatMarkdown from MarkdownContent

**Files:**
- Modify: `web/src/components/shared/MarkdownContent.tsx:143-148`

- [ ] **Step 1: Remove normalizeChatMarkdown call**

In `web/src/components/shared/MarkdownContent.tsx`, change:

```typescript
// BEFORE:
const sanitized = useMemo(
  () => sanitizeAssistantDisplayText(text, streaming),
  [text, streaming],
);
const normalized = useMemo(
  () => normalizeChatMarkdown(sanitized, streaming ? "streaming" : "final"),
  [sanitized, streaming],
);

if (!normalized.trim()) {
  return <p className={cn("m-0", mutedText)}>等待回答…</p>;
}

return (
  <div className="markdown-body">
    <ReactMarkdown ...>
      {normalized}
    </ReactMarkdown>
  </div>
);

// AFTER:
const sanitized = useMemo(
  () => sanitizeAssistantDisplayText(text, streaming),
  [text, streaming],
);

if (!sanitized.trim()) {
  return <p className={cn("m-0", mutedText)}>等待回答…</p>;
}

return (
  <div className="markdown-body">
    <ReactMarkdown ...>
      {sanitized}
    </ReactMarkdown>
  </div>
);
```

- [ ] **Step 2: Remove import**

Remove this line from `MarkdownContent.tsx`:

```typescript
import { normalizeChatMarkdown } from "../../lib/normalize-chat-markdown";
```

- [ ] **Step 3: Verify it compiles**

Run: `cd web && npm run build`
Expected: No errors

- [ ] **Step 4: Run existing tests**

Run: `cd web && npm test`
Expected: Some tests in `normalize-chat-markdown.test.ts` will fail (expected — we'll delete that file in Phase 3)

- [ ] **Step 5: Commit**

```bash
git add web/src/components/shared/MarkdownContent.tsx
git commit -m "refactor(ui): remove normalizeChatMarkdown from rendering pipeline

Trust LLM markdown output directly. Delete aggressive normalization
that was breaking valid markdown structures (ADR-0053)."
```

---

## Task 8: Add Markdown Format Constraint to Prompt

**Files:**
- Modify: `lca/layer1_cognitive/brain/prompts/react_prompt.md`

- [ ] **Step 1: Add output format section**

Append to `lca/layer1_cognitive/brain/prompts/react_prompt.md`:

```markdown
## 输出格式

你的最终回答必须使用标准 Markdown 格式：
- 标题用 `#` / `##` / `###`，不要用 `===` 或纯文字
- 列表用 `-` 或 `1.`，不要用 `·` 或 `•`
- 加粗用 `**文字**`，不要用全角或其他符号
- 引用用 `>` 前缀
- 代码用 ``` 围栏
- 表格用 `| col | col |` 语法

不要使用 ASCII 艺术格式（如 `=====` 分隔线、`·` 子列表）。
```

- [ ] **Step 2: Commit**

```bash
git add lca/layer1_cognitive/brain/prompts/react_prompt.md
git commit -m "docs(prompt): add markdown output format constraint

Instruct LLM to output standard markdown (headers, lists, bold)
instead of ASCII art formatting. Ensures proper rendering in UI."
```

---

## Task 9: Integrate MessageProjector into App.tsx with Feature Flag

**Files:**
- Modify: `web/src/shell/App.tsx`

- [ ] **Step 1: Add MessageProjector import and ref**

```typescript
import { MessageProjector } from "../projectors/message-projector";

// Inside App component:
const messageProjector = useRef(new MessageProjector());
```

- [ ] **Step 2: Feed events to MessageProjector**

In the event handler where `chatProjector` and `turnTimelineProjector` are called:

```typescript
const turn = messageProjector.current.onEvent(stamped);
```

- [ ] **Step 3: Add feature flag check**

```typescript
const useMessageRenderer = useFeatureFlag("message-renderer");
```

- [ ] **Step 4: Conditionally render MessageList**

```typescript
{useMessageRenderer ? (
  <MessageList turn={turn} />
) : (
  <LegacyThreadView timeline={timeline} trace={trace} />
)}
```

- [ ] **Step 5: Verify it compiles**

Run: `cd web && npm run build`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add web/src/shell/App.tsx
git commit -m "feat(ui): integrate MessageProjector with feature flag

Add MessageProjector alongside existing projectors. Feature flag
'message-renderer' controls new/old rendering switch (ADR-0053 Phase 2)."
```

---

## Task 10: Delete Legacy Code (Phase 3)

**Files:**
- Delete: `web/src/lib/normalize-chat-markdown.ts`
- Delete: `web/src/lib/normalize-chat-markdown.test.ts`
- Delete: `web/src/projectors/chat-projector.ts`
- Delete: `web/src/projectors/turn-timeline-projector.ts`
- Delete: `web/src/components/turn/AssistantTurnView.tsx`
- Delete: `web/src/components/turn/block-registry.tsx`
- Modify: `web/src/shell/App.tsx` (remove feature flag, use MessageProjector only)

- [ ] **Step 1: Delete legacy files**

```bash
rm web/src/lib/normalize-chat-markdown.ts
rm web/src/lib/normalize-chat-markdown.test.ts
rm web/src/projectors/chat-projector.ts
rm web/src/projectors/turn-timeline-projector.ts
rm web/src/components/turn/AssistantTurnView.tsx
rm web/src/components/turn/block-registry.tsx
```

- [ ] **Step 2: Simplify App.tsx**

Remove `chatProjector` and `turnTimelineProjector` refs. Remove feature flag check. Use `MessageProjector` and `MessageList` only.

- [ ] **Step 3: Run all tests**

Run: `cd web && npm test`
Expected: All tests pass

- [ ] **Step 4: Verify build**

Run: `cd web && npm run build`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(ui): delete legacy projector and rendering code

Remove ChatProjector, TurnTimelineProjector, normalizeChatMarkdown,
and old rendering components. MessageProjector + MessageList are now
the sole rendering pipeline (ADR-0053 Phase 3 complete)."
```

---

## Summary

**Total tasks:** 10
**Estimated time:** 4-6 hours
**Key deliverables:**
- MessageProjector replaces ChatProjector + TurnTimelineProjector
- MessageList + MessageRenderer provide LobeHub-style message flow
- Existing ThinkingPanel/ToolCallCard/WorkflowCollapse reused via adapters
- normalizeChatMarkdown deleted — trust LLM markdown output
- Prompt constraint ensures LLM outputs standard markdown

**Testing strategy:** TDD throughout — write tests first, implement second, commit after each task passes.
