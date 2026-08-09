import { describe, expect, it } from "vitest";
import type { Message } from "../../../projectors/message-types";
import {
  toSandboxBlock,
  toThinkingBlock,
  toToolBlock,
} from "../message-block-adapters";

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: "msg-1",
    kind: "thinking",
    content: "",
    streaming: false,
    status: "done",
    startedAt: 1000,
    ...overrides,
  };
}

describe("toThinkingBlock", () => {
  it("maps a streaming message to status running", () => {
    const msg = makeMessage({ streaming: true, content: "pondering…" });
    const block = toThinkingBlock(msg);

    expect(block.kind).toBe("thinking");
    expect(block.id).toBe("msg-1");
    expect(block.status).toBe("running");
    expect(block.content).toBe("pondering…");
  });

  it("maps a finished message to status done with durationMs", () => {
    const msg = makeMessage({
      streaming: false,
      content: "thought",
      metadata: { durationMs: 420 },
    });
    const block = toThinkingBlock(msg);

    expect(block.status).toBe("done");
    expect(block.durationMs).toBe(420);
  });

  it("omits durationMs when metadata is absent", () => {
    const block = toThinkingBlock(makeMessage());
    expect(block.durationMs).toBeUndefined();
  });
});

describe("toToolBlock", () => {
  it("maps all fields from metadata", () => {
    const msg = makeMessage({
      kind: "tool_call",
      status: "done",
      agentRole: "coder",
      metadata: {
        toolName: "read_file",
        argumentsPreview: "/etc/hosts",
        resultPreview: "127.0.0.1 localhost",
        ok: true,
        latencyMs: 12,
        invocationId: "inv-9",
      },
    });
    const block = toToolBlock(msg);

    expect(block).toEqual({
      kind: "tool",
      id: "msg-1",
      status: "done",
      toolName: "read_file",
      argumentsPreview: "/etc/hosts",
      resultPreview: "127.0.0.1 localhost",
      ok: true,
      latencyMs: 12,
      error: undefined,
      invocationId: "inv-9",
      agentRole: "coder",
    });
  });

  it("defaults missing metadata fields to empty strings", () => {
    const msg = makeMessage({ kind: "tool_call", status: "running" });
    const block = toToolBlock(msg);

    expect(block.toolName).toBe("");
    expect(block.argumentsPreview).toBe("");
    expect(block.resultPreview).toBe("");
    expect(block.invocationId).toBe("");
    expect(block.status).toBe("running");
  });

  it("preserves error status and error message", () => {
    const msg = makeMessage({
      kind: "tool_call",
      status: "error",
      metadata: { error: "boom", toolName: "flaky" },
    });
    const block = toToolBlock(msg);

    expect(block.status).toBe("error");
    expect(block.error).toBe("boom");
  });
});

describe("toSandboxBlock", () => {
  it("maps a sealed sandbox to done", () => {
    const msg = makeMessage({
      kind: "sandbox",
      agentRole: "executor",
      metadata: {
        invocationId: "sb-1",
        stdout: "hello\n",
        stderr: "",
        sealed: true,
      },
    });
    const block = toSandboxBlock(msg);

    expect(block).toEqual({
      kind: "sandbox",
      id: "msg-1",
      status: "done",
      invocationId: "sb-1",
      stdout: "hello\n",
      stderr: "",
      sealed: true,
      agentRole: "executor",
    });
  });

  it("maps an unsealed sandbox to running", () => {
    const msg = makeMessage({
      kind: "sandbox",
      metadata: { stdout: "partial", stderr: "warn" },
    });
    const block = toSandboxBlock(msg);

    expect(block.status).toBe("running");
    expect(block.sealed).toBe(false);
    expect(block.stdout).toBe("partial");
    expect(block.stderr).toBe("warn");
  });

  it("defaults missing metadata to empty strings and false", () => {
    const block = toSandboxBlock(makeMessage({ kind: "sandbox" }));

    expect(block.invocationId).toBe("");
    expect(block.stdout).toBe("");
    expect(block.stderr).toBe("");
    expect(block.sealed).toBe(false);
  });
});
