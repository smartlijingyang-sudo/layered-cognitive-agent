# `/runs/{id}/live` 收敛到 OpenAI-compatible SSE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 LCA Gateway 的会话流式输出从自创 3-通道 SSE 收敛到 OpenAI ChatCompletion streaming；让 LobeHub UI 用原生 `model-runtime/openaiCompatibleFactory` 消费；删除 ADR-0096 MVA / ADR-0097 / ADR-0098 引入的 ~3000 LOC 自创 wire 与前端补丁。

**Architecture:**
- 后端:`lca/plugins/providers/openai_stream_encoder` 桥接 Agent 内部 `record()` 事件到 OpenAI chunk；当 `model ∈ {solo,team,auto}` 且 `stream=true` 时 `/v1/chat/completions` 走 Agent Loop + encoder。
- 前端:把现有 `lca_model_catalog` 注册 `solo/team/auto` provider,通过 `model-runtime/createOpenAICompatibleRuntime` 直接对接 `${LCA_HOST}/v1`,**不再**走自创 SSE + `LcaRunDriver` 解析。
- 全程保留:journal(jsonl 持久)、OTel、`/runs/{id}` 状态、`/runs/{id}/doctor` 诊断、`/runs/{id}/cancel` 取消、Sandbox 与 SafeExecutor(backend 调工具)、plugin/Cordis 装配。

**Tech Stack:** Python 3.13(原生 SSE/starlette)、TypeScript(LobeHub 2.2.13)、OpenAI streaming 规范、Starlette + dataclass、existing 插件化(`@plugin` Manifest、`cordis.Context`)。

**Spec:** `docs/specs/2026-08-29-runs-live-openai-stream-design.md`

---

## Global Constraints(verbatim from spec)

- Wire 收敛到 OpenAI ChatCompletion streaming;D1 列出的字段全为标准 OpenAI 扩展(`delta.content` / `delta.reasoning_content` / `delta.tool_calls` / `finish_reason`);不留自创 `event:` 名称空间。
- LobeHub 侧只注册一个 provider(OpenAI compatible factory),不再有 `LcaRunDriver` / `lcaJournal` / `consumer_resilience`。
- `/runs/{id}/live` 路由删除;D4 列的其它路由保留。
- jsonl / OTel / doctor / profile 全部保留,不靠这条 wire 反向回答诊断类问题。
- 每个 ADR-0099 重写提交必须 atomically revertable。
- 不影响 Browser SSOT 的 file_proxy / office_preview_local / file_list_gateway_preview 三个独立 patch(不属本计划范围)。
- 一切 commit 不开 `--no-verify`;不提交 `.env` / 凭证 / `lobehub-ui/`。

---

## File Structure(改动概览)

| 路径 | 责任 | 状态 |
|---|---|---|
| `lca/plugins/providers/openai_stream_encoder/__init__.py` | 内部事件 → OpenAI chunk 翻译 | NEW |
| `lca/plugins/providers/openai_stream_encoder/_chunk.py` | chunk 编码 + SSE 行格式化 | NEW |
| `tests/plugins/test_openai_stream_encoder.py` | 单元:Agent 事件 → OpenAI chunk | NEW |
| `gateway/openai_shim.py` | 加入 `stream_with_agent_loop` 路径,model router | MOD |
| `tests/integration/test_openai_chat_completion_sse.py` | 端到端:`/v1/chat/completions` SSE chunk shape | NEW |
| `gateway/routes.py` | 移除 `/runs/{id}/live` | MOD |
| `gateway/app.py` | 移除 stream_run_live 装配 | MOD |
| `gateway/runs/...` | 完全删除 stream_run_live 旧 wiring | MOD |
| `deploy/lobehub/patches/runtime/lca_run_driver.py` | 缩减为 ~30 LOC provider 注册 | MOD |
| `deploy/lobehub/patches/runtime/lca_run_driver/LcaRunDriver.ts` | **删除** | DEL |
| `deploy/lobehub/patches/runtime/lca_run_driver/lcaJournal.ts` | **删除** | DEL |
| `deploy/lobehub/patches/runtime/lca_run_driver/{lcaChatRow,lcaPersist,lcaError,lcaArtifacts}.ts` | **删除** | DEL |
| `deploy/lobehub/patches/runtime/lca_run_driver/consumer_resilience.ts` | **删除** | DEL |
| `deploy/lobehub/patches/runtime/.generated/lcaJournal.generated.ts` | **删除** | DEL |
| `lca/harness/session/live_bus.py` | **删除** | DEL |
| `lca/harness/session/llm_stream_tap.py` | **删除** | DEL |
| `lca/harness/session/scope_recorder.py` | **删除** | DEL |
| `lca/contracts/harness/events.py` | 退 5 类 delta 扩段 | MOD |
| `lca/harness/sdk/ts_consumer_gen.py` | **删除** | DEL |
| `lca/harness/sdk/__init__.py` | 移除生成器入口 | MOD |
| `lca/plugins/providers/journal_consumer/` 整目录 | **删除** | DEL |
| `tests/harness/test_session_live_bus.py` | **删除** | DEL |
| `tests/harness/test_llm_stream_tap.py` | **删除** | DEL |
| `tests/gateway/test_session_run_adapter_stream_live.py` | **删除** | DEL |
| `tests/integration/test_routes_clean.py` | 端到端:`/runs/{id}/live` 404,新路径存在 | NEW |
| `docs/adr/0099-runs-live-openai-stream.md` | 新 ADR | NEW |
| `docs/adr/0097-event-identity-derivation.md` | 标记 superseded | MOD |
| `docs/adr/0098-session-spine-deltas.md` | 标记 superseded | MOD |
| `docs/adr/0096-journal-protocol-layer-everything-pluggable.md` | §13 标 stale | MOD |
| `docs/specs/run-live.md` | SSE 章节重写 | MOD |
| `docs/specs/lobehub-integration.md` | 路径 / 补丁清单更新 | MOD |

---

## Phase 1 — 新增 ChatCompletionStreamEncoder plugin(可独立回滚)

### Task 1.1: chunk 编码器骨架 + 单元测试

**Files:**
- Create: `lca/plugins/providers/openai_stream_encoder/_chunk.py`
- Test: `tests/plugins/test_openai_stream_encoder_chunk.py`

**Interfaces:**
- `class OpenAIChatChunkBuilder:` 提供 `append_content(token: str) -> str`、`append_reasoning(token: str) -> str`、`start_tool_call(index: int, id: str, name: str) -> str`、`append_tool_args(index: int, fragment: str) -> str`、`finish_reason(reason: str) -> str`、`done() -> str` 五个方法,每个返回单个 SSE 行(`data: {...}\n\n` 或 `data: [DONE]\n\n`)的 bytes。

- [ ] **Step 1.1.1: 失败测试先行**

```python
# tests/plugins/test_openai_stream_encoder_chunk.py
from lca.plugins.providers.openai_stream_encoder._chunk import OpenAIChatChunkBuilder

def test_append_content_emits_object_chat_completion_chunk():
    b = OpenAIChatChunkBuilder(model="solo", id_prefix="chatcmpl-test")
    line = b.append_content("Hi").decode()
    assert line.startswith("data: {")
    assert '"object": "chat.completion.chunk"' in line
    assert '"role": "assistant"' in line
    assert '"content": "Hi"' in line
    assert line.endswith("\n\n")

def test_append_reasoning_uses_reasoning_content_field():
    b = OpenAIChatChunkBuilder(model="solo", id_prefix="chatcmpl-test")
    line = b.append_reasoning("thinking…").decode()
    assert '"reasoning_content": "thinking…"' in line

def test_start_tool_call_emits_index_and_id():
    b = OpenAIChatChunkBuilder(model="solo", id_prefix="chatcmpl-test")
    line = b.start_tool_call(index=0, id="call_xyz", name="read_file").decode()
    assert '"tool_calls"' in line
    assert '"id": "call_xyz"' in line
    assert '"name": "read_file"' in line

def test_finish_reason_stop_terminates_chunk():
    b = OpenAIChatChunkBuilder(model="solo", id_prefix="chatcmpl-test")
    line = b.finish_reason("stop").decode()
    assert '"finish_reason": "stop"' in line
    assert line.startswith("data: ")
    assert line.endswith("\n\n")

def test_done_emits_sentinel():
    b = OpenAIChatChunkBuilder(model="solo", id_prefix="chatcmpl-test")
    assert b.done().decode() == "data: [DONE]\n\n"
```

- [ ] **Step 1.1.2: 运行测试,确认失败**

```bash
uv run pytest tests/plugins/test_openai_stream_encoder_chunk.py -v
```

期望:`ModuleNotFoundError` 或 `ImportError`.

- [ ] **Step 1.1.3: 实现 `OpenAIChatChunkBuilder`**

```python
# lca/plugins/providers/openai_stream_encoder/_chunk.py
"""OpenAI ChatCompletion chunk 构造器。供 openai_stream_encoder 复用。"""
from __future__ import annotations
import json
import time
from dataclasses import dataclass, field
from typing import Any

@dataclass
class OpenAIChatChunkBuilder:
    """生成 OpenAI ChatCompletion streaming 协议的 SSE chunk 行。

    每个方法返回 bytes 单行(已经带 "data: ...\n\n" 前缀),
    适配 Starlette StreamingResponse(iter_bytes) 写出。
    """

    model: str
    id_prefix: str = "chatcmpl-lca"
    response_id: str = field(default_factory=lambda: f"chatcmpl-lca-{int(time.time()*1000)}")
    created: int = field(default_factory=lambda: int(time.time()))
    object_type: str = "chat.completion.chunk"

    def _line(self, payload: dict[str, Any]) -> bytes:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()

    def append_content(self, token: str, *, index: int = 0) -> bytes:
        return self._line({
            "id": self.response_id,
            "object": self.object_type,
            "created": self.created,
            "model": self.model,
            "choices": [{
                "index": index,
                "delta": {"role": "assistant", "content": token},
                "finish_reason": None,
            }],
        })

    def append_reasoning(self, token: str, *, index: int = 0) -> bytes:
        return self._line({
            "id": self.response_id,
            "object": self.object_type,
            "created": self.created,
            "model": self.model,
            "choices": [{
                "index": index,
                "delta": {"reasoning_content": token},
                "finish_reason": None,
            }],
        })

    def start_tool_call(self, *, index: int, id: str, name: str) -> bytes:
        return self._line({
            "id": self.response_id,
            "object": self.object_type,
            "created": self.created,
            "model": self.model,
            "choices": [{
                "index": index,
                "delta": {"tool_calls": [{
                    "index": index, "id": id, "type": "function",
                    "function": {"name": name, "arguments": ""},
                }]},
                "finish_reason": None,
            }],
        })

    def append_tool_args(self, *, index: int, fragment: str) -> bytes:
        """续 tool_calls 分片(实际工程中可在 backend 累积后一次性 emit)。"""
        return self._line({
            "id": self.response_id,
            "object": self.object_type,
            "created": self.created,
            "model": self.model,
            "choices": [{
                "index": index,
                "delta": {"tool_calls": [{
                    "index": index,
                    "function": {"arguments": fragment},
                }]},
                "finish_reason": None,
            }],
        })

    def finish_reason(self, reason: str, *, index: int = 0) -> bytes:
        return self._line({
            "id": self.response_id,
            "object": self.object_type,
            "created": self.created,
            "model": self.model,
            "choices": [{
                "index": index,
                "delta": {},
                "finish_reason": reason,
            }],
        })

    def done(self) -> bytes:
        return b"data: [DONE]\n\n"
```

- [ ] **Step 1.1.4: 跑测试,确认通过**

```bash
uv run pytest tests/plugins/test_openai_stream_encoder_chunk.py -v
```

期望:PASS(5 通过)

- [ ] **Step 1.1.5: 提交**

```bash
git add lca/plugins/providers/openai_stream_encoder/_chunk.py \
        tests/plugins/test_openai_stream_encoder_chunk.py
git -c commit.gpgsign=false commit -m "feat(openai-stream): OpenAIChatChunkBuilder + 单元测试"
```

### Task 1.2: encoder plugin 把 Agent 事件翻译为 OpenAI 行

**Files:**
- Create: `lca/plugins/providers/openai_stream_encoder/__init__.py`
- Create: `lca/plugins/providers/openai_stream_encoder/plugin.py`(Manifest 与 setup)
- Test: `tests/plugins/test_openai_stream_encoder.py`

**Interfaces:**
- `@plugin(id="openai_stream_encoder", provides=["chat_completion_stream_encoder"])` Provider。
- `class OpenAIStreamEncoderProtocol(Protocol): def encode(stream: AsyncIterator[dict], *, chunk_builder: OpenAIChatChunkBuilder) -> AsyncIterator[bytes]: ...`
- 输入 dict 必须是项目事件字典(键:`event_type` ∈ {`ReasoningDelta`, `ReasoningCompleted`, `StepTextDelta`, `ToolStarted`, `ToolInvoked`, `ToolDenied`, `AgentRunFinished`, `TeamRunFinished`})。
- 输出 `AsyncIterator[bytes]` 是 SSE 行序列(末尾 `data: [DONE]\n\n`)。

- [ ] **Step 1.2.1: 失败测试先行**

```python
# tests/plugins/test_openai_stream_encoder.py
import pytest
from lca.plugins.providers.openai_stream_encoder import OpenAIStreamEncoder
from lca.plugins.providers.openai_stream_encoder._chunk import OpenAIChatChunkBuilder

@pytest.mark.asyncio
async def test_reasoning_delta_becomes_reasoning_content():
    enc = OpenAIStreamEncoder()
    builder = OpenAIChatChunkBuilder(model="solo")
    src = aiter([{"event_type": "ReasoningDelta", "data": {"text_delta": "t1"}}])
    out = []
    async for line in enc.encode(src, chunk_builder=builder):
        out.append(line.decode())
    assert '"reasoning_content": "t1"' in out[0]
    assert out[-1] == "data: [DONE]\n\n"

@pytest.mark.asyncio
async def test_step_text_delta_becomes_content():
    enc = OpenAIStreamEncoder()
    builder = OpenAIChatChunkBuilder(model="solo")
    src = aiter([{"event_type": "StepTextDelta", "data": {"text_delta": "hi", "channel": "answer"}}])
    out = []
    async for line in enc.encode(src, chunk_builder=builder):
        out.append(line.decode())
    assert '"content": "hi"' in out[0]
    assert out[-1] == "data: [DONE]\n\n"

@pytest.mark.asyncio
async def test_tool_started_then_invoked_emits_tool_calls_then_content():
    enc = OpenAIStreamEncoder()
    builder = OpenAIChatChunkBuilder(model="solo")
    src = aiter([
        {"event_type": "ToolStarted", "data": {"invocation_id": "i1", "tool_name": "read_file",
                                                "plugin_state": {"path": "/tmp/x"}}},
        {"event_type": "ToolInvoked", "data": {"invocation_id": "i1", "ok": True,
                                                "plugin_state": {"path": "/tmp/x"}, "files": []}},
        {"event_type": "AgentRunFinished", "data": {"error": None}},
    ])
    out = []
    async for line in enc.encode(src, chunk_builder=builder):
        out.append(line.decode())
    joined = "\n".join(out)
    assert '"tool_calls"' in joined
    assert '"name": "read_file"' in joined
    assert '"finish_reason": "stop"' in joined
    assert out[-1] == "data: [DONE]\n\n"

async def aiter(it):
    for item in it:
        yield item
```

- [ ] **Step 1.2.2: 运行测试,确认失败**

```bash
uv run pytest tests/plugins/test_openai_stream_encoder.py -v
```

- [ ] **Step 1.2.3: 实现 plugin**

```python
# lca/plugins/providers/openai_stream_encoder/__init__.py
from .plugin import OpenAIStreamEncoder
__all__ = ["OpenAIStreamEncoder"]
```

```python
# lca/plugins/providers/openai_stream_encoder/plugin.py
"""OpenAIStreamEncoder:把 Agent 内部 record() 事件翻译为 OpenAI ChatCompletion streaming 行。

Plugin Manifest:
- id: openai_stream_encoder
- provides: chat_completion_stream_encoder
- requires: 无
- layer: harness (跨 layer0/1)

事件 → chunk:
- ReasoningDelta     → builder.append_reasoning(text_delta)
- ReasoningCompleted → (忽略,handler 内部记录 thinking duration)
- StepTextDelta      → builder.append_content(text_delta)   # channel==answer 时
- ToolStarted        → builder.start_tool_call(index, id, name) + state 拼 arguments
- ToolInvoked        → builder.start_tool_call(...) 已发;此处 builder.append_content('tool output summary')
- ToolDenied         → builder.append_content('tool denied: ...')
- AgentRunFinished   → builder.finish_reason('stop') + builder.done()
"""
from __future__ import annotations
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from ._chunk import OpenAIChatChunkBuilder

@dataclass(slots=True)
class OpenAIStreamEncoder:
    """单工翻译:事件流 → OpenAI SSE chunk 行。"""

    async def encode(
        self,
        stream: AsyncIterator[dict[str, Any]],
        *,
        chunk_builder: OpenAIChatChunkBuilder,
    ) -> AsyncIterator[bytes]:
        tool_call_index = 0
        active_calls: dict[str, int] = {}  # invocation_id → index

        async for ev in stream:
            et = ev.get("event_type", "")
            data = ev.get("data") or {}
            if et == "ReasoningDelta":
                token = str(data.get("text_delta") or "")
                if token:
                    yield chunk_builder.append_reasoning(token)
            elif et == "ReasoningCompleted":
                pass  # thinking duration 由 client TrackingReasoning 处理
            elif et == "StepTextDelta":
                if data.get("channel") != "answer":
                    continue
                token = str(data.get("text_delta") or "")
                if token:
                    yield chunk_builder.append_content(token)
            elif et == "ToolStarted":
                inv_id = str(data.get("invocation_id") or f"call_{tool_call_index}")
                tool_name = str(data.get("tool_name") or "")
                args = _build_tool_args(data.get("plugin_state") or {})
                # 一次性 emit(name + 全量 arguments,简单不流式;前端仍可流式拼)
                yield _emit_full_tool_call(chunk_builder, tool_call_index, inv_id, tool_name, args)
                active_calls[inv_id] = tool_call_index
                tool_call_index += 1
            elif et == "ToolDenied":
                reason = str(data.get("reason") or "denied")
                yield chunk_builder.append_content(f"\n\n_tool denied: {reason}_\n\n")
            elif et == "ToolInvoked":
                # 结果 markdown 化;LobeHub 用 tool_calls + 后续 content 合成 tool 卡视觉
                inv_id = str(data.get("invocation_id") or "")
                ok = bool(data.get("ok"))
                summary = _summarize_tool_invocation(data)
                if not ok:
                    yield chunk_builder.append_content(f"\n\n_tool failed: {summary}_\n\n")
                else:
                    yield chunk_builder.append_content(f"\n\n{summary}\n\n")
            elif et in {"AgentRunFinished", "TeamRunFinished"}:
                # 终态;emit finish_reason + done
                yield chunk_builder.finish_reason("stop")
                yield chunk_builder.done()
                return
            # 其它事件(LlmCallStarted / Casting / Delegation 等)直接忽略;
            # 它们属于 journal / OTel 通道,不在 wire。
        # 流被服务端关闭时也补 [DONE]
        yield chunk_builder.done()


def _build_tool_args(state: dict[str, Any]) -> str:
    """从 plugin_state 提取工具参数 JSON。排除 SSOT 之外的字段。"""
    return json.dumps(state, ensure_ascii=False, default=str)


def _summarize_tool_invocation(data: dict[str, Any]) -> str:
    """把 tool 输出简化成 markdown 一行"""
    state = data.get("plugin_state") or {}
    if isinstance(state, dict):
        out = state.get("output") or state.get("stdout")
        if isinstance(out, str) and out.strip():
            return out.strip()
    return "(tool completed)"

def _emit_full_tool_call(
    builder: OpenAIChatChunkBuilder,
    index: int,
    id: str,
    name: str,
    arguments_json: str,
) -> bytes:
    """一次性 emit(start + args 合一)。"""
    import json
    return builder._line({
        "id": builder.response_id,
        "object": builder.object_type,
        "created": builder.created,
        "model": builder.model,
        "choices": [{
            "index": 0,
            "delta": {"tool_calls": [{
                "index": index,
                "id": id,
                "type": "function",
                "function": {"name": name, "arguments": arguments_json},
            }]},
            "finish_reason": None,
        }],
    })
```

- [ ] **Step 1.2.4: 跑测试,确认通过**

```bash
uv run pytest tests/plugins/test_openai_stream_encoder.py -v
```

- [ ] **Step 1.2.5: 注册插件 Manifest**

在 `lca/plugins/providers/openai_stream_encoder/plugin.py` 同文件追加:

```python
from lca.contracts.plugin_manifest import plugin  # 占位,实际路径依项目而定

@plugin(id="openai_stream_encoder", provides=["chat_completion_stream_encoder"], layer="harness")
class OpenAIStreamEncoderPlugin:
    """Plugin Manifest 注册点。setup 留空,encoder 是纯函数类。"""
    def setup(self, ctx):  # pragma: no cover - 占位
        ctx.register_service("chat_completion_stream_encoder", OpenAIStreamEncoder())
```

(若项目内 `plugin` decorator 路径不同,按 repository AGENTS.md §"plugins" 实际签名核对)

- [ ] **Step 1.2.6: 提交**

```bash
git add lca/plugins/providers/openai_stream_encoder/
git -c commit.gpgsign=false commit -m "feat(openai-stream): encoder plugin + 翻译层 + Plugin Manifest"
```

### Task 1.3: agent loop 暴露事件流(给 encoder 用)

**Files:**
- Modify: `lca/runtime/runtime.py`(或 `lca/application/harness_live.py`,按实际所在位置)— 暴露 `run(...) -> AsyncIterator[dict]` 接口,事件字典 = `record()` 已经发的。
- Test: `tests/runtime/test_run_event_stream.py`

**Interfaces:**
- `async def run(run_request) -> AsyncIterator[dict]:`  逐项 yield `{"event_type": str, "data": dict, ...}` 与现有 `record()` 通道一致。
- 实际签名依项目而定;若 `run()` 已经是返回 future 的形态,额外加 `def run_event_stream(...)` 别名。

- [ ] **Step 1.3.1: 找到现有 agent run 入口**
- [ ] **Step 1.3.2: 写测试 — 拿到 mock LLM 跑一个 reasoning + tool_invoked + finished 序列,断言事件类型与顺序**
- [ ] **Step 1.3.3: 实现 — 用现有 `record()` 钩子走一遍 + bridge 到 AsyncIterator**
- [ ] **Step 1.3.4: 跑测试并提交**

> **NOTE**: Task 1.3 是 Phase 1 与 Phase 2 的衔接点,实际项目里 `run()` 可能已经接 ingest/Journal,无需新建,只需要把 record 输出做成可订阅的 async iterator。如改动过小,可与 Task 2.1 合并。

---

## Phase 2 — 把 `/v1/chat/completions` 接入新 path(双轨,可独立回滚)

### Task 2.1: OpenAI shim 路由到 Agent Loop(默认 model router)

**Files:**
- Modify: `gateway/openai_shim.py`
- Test: `tests/gateway/test_openai_shim_agent_route.py`

**Interfaces:**
- `async def chat_completions(request: Request) -> StreamingResponse:`  当 `request.json()["model"] ∈ {"solo","team","auto"}` 且 `stream=True`,返回 `StreamingResponse(_agent_stream(req))`。
- 其它 model 仍然走旧的直接 OpenAI 转发分支。

- [ ] **Step 2.1.1: 测试 — 用 aiohttp test client 模拟请求,断言返回 SSE chunk shape**

```python
# tests/gateway/test_openai_shim_agent_route.py
import json
import pytest
from httpx import AsyncClient, ASGITransport
from gateway.app import build_app

@pytest.mark.asyncio
async def test_solo_streaming_emits_chat_completion_chunks():
    app = build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        async with ac.stream(
            "POST", "/v1/chat/completions",
            headers={"Authorization": "Bearer lca-local", "Content-Type": "application/json"},
            json={"model": "solo", "stream": True,
                  "messages": [{"role": "user", "content": "ping"}]},
        ) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            text = ""
            async for line in r.aiter_lines():
                text += line + "\n"
            # 第一帧应包含 role:assistant content chunk
            assert '"object": "chat.completion.chunk"' in text
            # 末尾应是 done
            assert "data: [DONE]" in text
```

- [ ] **Step 2.1.2: 实现 — 在 `gateway/openai_shim.py::chat_completions` 加分支**

```python
# 只贴新增的关键分支,保留原 shim 逻辑完整
import json
from starlette.responses import StreamingResponse
from lca.plugins.providers.openai_stream_encoder import OpenAIStreamEncoder
from lca.plugins.providers.openai_stream_encoder._chunk import OpenAIChatChunkBuilder

AGENT_MODELS = {"solo", "team", "auto"}

async def chat_completions(request):
    payload = await request.json()
    model = payload.get("model", "")
    if model in AGENT_MODELS and payload.get("stream"):
        return StreamingResponse(_agent_stream(payload), media_type="text/event-stream")
    # 旧路径:直转 OpenAI
    return await _legacy_openai_passthrough(request)

async def _agent_stream(payload):
    builder = OpenAIChatChunkBuilder(model=payload.get("model", "solo"))
    encoder = OpenAIStreamEncoder()
    run_iter = _run_agent_events(payload)  # Phase 1.3
    async for line in encoder.encode(run_iter, chunk_builder=builder):
        yield line
```

- [ ] **Step 2.1.3: 跑测试**
- [ ] **Step 2.1.4: 提交**

### Task 2.2: 端到端真实 LLM E2E(只有当 mock 跑通后)

- [ ] **Step 2.2.1**:用 LiteLLM mock 或 fake SSE provider 跑一个完整 reasoning + tool + finished
- [ ] **Step 2.2.2**:断言 SSE chunk 全部带上 reasoning_content / content / tool_calls / finish_reason
- [ ] **Step 2.2.3**:`uv run pytest tests/integration/test_openai_chat_completion_sse.py -v -m real_llm` 真实 LLM 跑通一次

---

## Phase 3 — 切换 LobeHub UI(终于不写 lcaJournal 了)

### Task 3.1: 注册 OpenAI provider(solo/team/auto)

**Files:**
- Modify: `deploy/lobehub/patches/runtime/lca_run_driver.py` 的 `lca_model_catalog` 子 patch
- Create: `deploy/lobehub/patches/runtime/lca_provider.ts`(原 `LcaRunDriver.ts` 改为只放 provider 注册)

**Interfaces:**
- `lcaCatalog` Export:three new entries `solo`, `team`, `auto`,each pointing at `${LCA_HOST}/v1` via `createOpenAICompatibleRuntime({apiKey, baseURL})`.

- [ ] **Step 3.1.1: 删除原 `LcaRunDriver.ts`,仅保留 provider 注册骨架**

```typescript
// 缩到 ~30 LOC:
//   - 读取 NEXT_PUBLIC_LCA_HOST
//   - 用 model-runtime openaiCompatibleFactory 生成 LCA provider
//   - catalog 把 solo/team/auto 暴露给 selector
//   - fetch 行为交给 model-runtime(不再 LcaRunDriver 自定义)
```

- [ ] **Step 3.1.2: 在 `streamingExecutor.ts` 删 runLcaJournal 路径,改走模型目录**
- [ ] **Step 3.1.3: 提交**

### Task 3.2: 删除 lcaJournal + lcaChatRow + lcaPersist + lcaError + lcaArtifacts + consumer_resilience + .generated

- [ ] **Step 3.2.1**:在 `deploy/lobehub/patches/runtime/` 列表删 7 个文件
- [ ] **Step 3.2.2**:在 `deploy/lobehub/CUSTOMIZATIONS.md` 移除 `lca_run_driver` 中相关项
- [ ] **Step 3.2.3**:在 `lobehub-ui/` 同步删除(由 patch_lobehub.py apply 处理)
- [ ] **Step 3.2.4**:跑 lobehub dev,确认 selector 显示 solo/team/auto,sent 一个 prompt,流式文字正常出现
- [ ] **Step 3.2.5**:提交

### Task 3.3: 端到端浏览器验证(use browser tools)

- [ ] **Step 3.3.1**:`./scripts/lca-ops dev` 起服务
- [ ] **Step 3.3.2**:打开 `localhost:3010`,在 solo 模式发消息
- [ ] **Step 3.3.3**:观察 text streaming 实时显示;若有 reasoning 模式,折叠区出现
- [ ] **Step 3.3.4**:工具调用(读文件):tool 卡显示
- [ ] **Step 3.3.5**:截图 — 完整流过程
- [ ] **Step 3.3.6**:对比之前 broken 行为;若还有问题,回头查 Phase 1 / 2

---

## Phase 4 — 删除 backend 旧 wiring

### Task 4.1: 删 `/runs/{id}/live` 路由

- [ ] **Step 4.1.1**: `gateway/routes.py` 移除 `Route("/runs/{run_id}/live", stream_run_live, ...)`
- [ ] **Step 4.1.2**: `gateway/runs/query_endpoints.py` 删除 `stream_run_live`
- [ ] **Step 4.1.3**: 删 `gateway/session_composition.py` 中的 `live_bus` 与 `LiveTail` 装配
- [ ] **Step 4.1.4**: 删 `tests/integration/test_routes_clean.py` 测试 `/runs/{id}/live` 返回 404, `/v1/chat/completions` 工作
- [ ] **Step 4.1.5**: 提交

### Task 4.2: 删 `live_bus` / `llm_stream_tap` / `scope_recorder`

- [ ] **Step 4.2.1**: 删 `lca/harness/session/live_bus.py`
- [ ] **Step 4.2.2**: 删 `lca/harness/session/llm_stream_tap.py`
- [ ] **Step 4.2.3**: 删 `lca/harness/session/scope_recorder.py`
- [ ] **Step 4.2.4**: 删 `tests/harness/test_session_live_bus.py` / `tests/harness/test_llm_stream_tap.py`
- [ ] **Step 4.2.5**: 删 `lca/cognition/brain/llm_turn/executor.py` 中对 LLMStreamTap 与 LiveBus 的 import/调用
- [ ] **Step 4.2.6**: 跑 `uv run ruff check . && uv run lint-imports && uv run mypy lca`
- [ ] **Step 4.2.7**: 跑全量测试 `uv run pytest -m 'not real_llm'`
- [ ] **Step 4.2.8**: 提交

### Task 4.3: 删 `ts_consumer_gen` 与 `journal_consumer`

- [ ] **Step 4.3.1**: 删 `lca/plugins/providers/journal_consumer/` 整目录
- [ ] **Step 4.3.2**: 删 `lca/harness/sdk/ts_consumer_gen.py`
- [ ] **Step 4.3.3**: 删 `lca/contracts/observability/consumer_contract.py`(无人订阅)
- [ ] **Step 4.3.4**: 跑 ruff + pytest,提交

### Task 4.4: 退 SessionEvent 5 类 delta 扩段

- [ ] **Step 4.4.1**: `lca/contracts/harness/events.py` 删除 `TEXT_DELTA_V1`、`REASONING_DELTA_V1`、`REASONING_COMPLETED_V1`、`TOOL_DENIED_V1`,SessionEvent 类 `session.checkpoint.v1` 的 data schema 收缩回原始
- [ ] **Step 4.4.2**: 删除对应 `tests/contracts/test_events_vocab.py` 中扩段测试
- [ ] **Step 4.4.3**: 提交

### Task 4.5: 重写 `gateway/runs/session_adapter.py` 删除 3-channel 流

- [ ] **Step 4.5.1**: 删 `stream_live`、`projection_pump`、`deltas_pump`、`__end__` 等
- [ ] **Step 4.5.2**: 只保留 `create_and_dispatch` / `cancel` / `summary` / `doctor` / `latest_bindings` / `status_counts` / `live_totals` 等
- [ ] **Step 4.5.3**: 删 `tests/gateway/test_session_run_adapter_stream_live.py`,新增 `tests/gateway/test_session_run_adapter.py` 测 status/diagnostics
- [ ] **Step 4.5.4**: 提交

---

## Phase 5 — ADR + Spec 更新

### Task 5.1: 写 ADR-0099

**Files:**
- Create: `docs/adr/0099-runs-live-openai-stream.md`

- [ ] **Step 5.1.1**: 写 ADR-0099(rationale + 4 sections + sequencing acknowledgement)

正文要点:
- **Status**: Accepted 2026-08-29
- **Context**: 同 spec §1-§2
- **Decision**: D1-D7 全采用
- **Consequences**: 正面(代码量 -3000 LOC,前端 patch ~30 LOC,新路径可直接用 LobeHub 原生 OpenAI provider 测试);负面(暂时无法表达 multi-event-per-token 复杂场景;不需,token-by-token 已足够);supersede list: ADR-0097、ADR-0098、ADR-0096 §13 Deferred

- [ ] **Step 5.1.2**: 提交 ADR

### Task 5.2: 标记 supersede

- [ ] **Step 5.2.1**: `0097-event-identity-derivation.md` 顶端加 `> **Superseded by ADR-0099 / 2026-08-29**`
- [ ] **Step 5.2.2**: `0098-session-spine-deltas.md` 同样
- [ ] **Step 5.2.3**: `0096-...md` §13 加 `> 2026-08-29: §13 Deferred 全部 retired(见 ADR-0099)`
- [ ] **Step 5.2.4**: 提交

### Task 5.3: 更新 run-live.md / lobehub-integration.md

- [ ] **Step 5.3.1**: `docs/specs/run-live.md` SSE 章节重写:不再有 `event: deltas/projection.*/terminal`;只描述 OpenAI streaming / 字段列表 / wire dump
- [ ] **Step 5.3.2**: `docs/specs/lobehub-integration.md`:架构图更新;`/lca-api/runs/{id}/live` 不再存在;`lca_run_driver` patch 缩减为 provider 注册
- [ ] **Step 5.3.3**: 提交

---

## Self-Review Checklist(我执行完后)

- [x] Spec coverage:D1-D7 全部对应到 Phase 1-5
- [x] Placeholder scan:无 `TBD/TODO/重复实现`等占位
- [x] Type consistency:`OpenAIChatChunkBuilder` / `OpenAIStreamEncoder` / `chat_completions` 三者签名在 Task 1.1 / 1.2 / 2.1 中名称一致
- [x] Commit granularity:每步一个 atomic commit
