# ADR-0188 — Session 标题事件:session.title.v1 词表 + 标题服务/LLM provider 插件

## 状态

Proposed(2026-09-05 起草)。本变更同 PR 落地词表注册、两个插件、测试与本草案
(AGENTS.md §3 C11:新 Session 事件必须带白名单 + 注册 + 测试 + ADR)。

**上游真值**:ADR-0186(Session 为事件 SSOT)。标题写入只经 `Session.append`,
事件词表注册在 `lca/contracts/harness/memory/events.py` 的 `@session_event` 白名单。

**对位参考**:deepseek-harness `packages/session/session-title{,-llm,-first-prompt-llm}`
与 `docs/subsystems/session-title.md`;LCA 规格 `docs/specs/session-event-pipeline-spec.md` §4.3。

## 0. 决策摘要

标题是**日志事件,不是旁路存储**:

```text
首条合格用户消息 ── 确定性回退标题 ──┐
可选 provider 生成 ── 校验后取代 ────┤→ Session.append("session.title.v1", …)
用户显式重命名 ── pin(停止自动) ────┘         │
                                              ↓
              fold latest-wins(get / UI 列表 / 未来消费方)
```

- 新词表:`session.title.v1`,payload `{title, message_seqs, source}`;
  `visibility="audit"`(非模型可见档),**log-only**,不进模型可见面与派生历史。
- `source` 闭集(字符串):`"fallback"`(内置确定性回退)/ `"provider"`
  (注册 provider 生成)/ `"user"`(显式重命名,pin)。
- 标题服务自身不调 LLM(`effects="none"`);LLM 调用收敛在独立
  provider 插件(`effects="network"`),插件间只经 capability `session.title` 交互。

## 1. 事件词定义(C11 四件套)

| 件 | 落点 |
|---|---|
| 白名单/注册 | `@session_event("session.title.v1", visibility="audit")` 于 `lca/contracts/harness/memory/events.py`(文件末尾追加,未改既有行) |
| 生产方 | `lca/plugins/session/title_service/`(唯一 append 方) |
| 测试 | `tests/contracts/test_session_title_event.py`(注册/可见性/frozen/JSON 回归锁)+ `tests/plugins/session/test_title_service.py` + `test_title_llm_provider.py` |
| ADR | 本文件 |

`SessionTitle` payload:`title: str`(归一化后非空)、`message_seqs: tuple[int, ...]`
(派生所用用户消息的事件 seq;用户重命名为空)、`source: str`。frozen dataclass +
基础类型,无损 JSON 可序列化(`Session.append` 的快照校验前置把守)。

## 2. 服务语义(对位 DSH `SessionTitleService`)

- **fold 读取**:`get(session)` 从 `snapshot_events()` 折叠最新标题事件,
  latest-wins;畸形事件跳过。
- **确定性回退**:首条合格用户消息(`message.accepted.v1` 且 `role="user"`、
  清洗后非空)→ 立即追加清洗(去 ANSI/控制/方向性字符、压缩空白)+
  词数/UTF-8 字节双上限(缺省 5 词 / 40 字节)的标题;仅在无标题时追加。
- **可选 provider**:同一时刻至多一个(重复注册抛 `ValueError`);
  first-prompt 节奏——仅首条合格用户消息触发;输出经服务侧校验
  (归一化非空、`message_seqs` 唯一有序且属本次请求快照、字节上限
  缺省 80)后以 `source="provider"` 取代回退。
- **验收/取代**:per-session 单调 revision;新调度 `Task.cancel` 旧在途并
  set 其 signal;过期完成结果丢弃;用户重命名先取代在途工作。
- **pin/解钉**:最新标题 `source="user"` 即钉住自动调度;`refresh` 是唯一
  有意解钉(无 provider 时重派回退覆盖钉住;有 provider 时重新调度)。
- **失败 contained**:observer / 延迟调度 / provider 一切失败只记
  structlog warning,绝不阻塞主响应,绝不反噬 `Session.append`。

## 3. 与 DSH 的偏差(显式)

| 偏差点 | DSH | LCA | 理由 |
|---|---|---|---|
| 用户消息事件 | `user/message`(内容块) | `message.accepted.v1`(`role="user"` + `content_ref`) | LCA 词表既有形态;不新增平行用户消息词 |
| `source` 形状 | 判别联合体(带 provider/model provenance) | 字符串三值闭集 | 事件 payload 保持 JSON 基础类型;provenance 不进词表 |
| 超长用户重命名 | 截断到上限后接受 | 拒绝(`ValueError`) | 显式输入宁可拒绝不静默改义 |
| provider 入参 | `request` 对象(含 route/AbortSignal) | `(session, messages, signal)`;signal 为 `asyncio.Event` | Python asyncio 原生取消经 `Task.cancel` 表达 |
| 主请求路由门 | 等 `request/header` 再启动生成 | 用户消息到达即异步启动 | LCA runtime Session 平面暂无请求路由事件 |
| LLM 调用 | `ctx.llm.stream`(framing/字节上限/finish 校验) | `llm.complete(prompt)` + `asyncio.wait_for` 超时 | LCA `LLMAdapter` 形态;极简 prompt 保留指令骨架 |
| 无事件循环 | N/A(fiber 恒在) | 同步上下文放弃本次调度(记日志) | `Session.append` 同步,无循环则无法延迟 append(重入拒绝) |

## 4. 消费方

- `SessionTitleService.get`:live fold(本 PR)。
- 未来 UI/会话列表:从 `snapshot_events()` 或持久化 `.session.jsonl` fold
  `session.title.v1`(latest-wins),与 DSH `title` projection 同形。
- 无模型可见消费方:`visibility="audit"` 保证不进入模型历史折叠。

## 5. 插件声明

| plugin | provides | requires | effects | 说明 |
|---|---|---|---|---|
| `lca.plugins.session.title_service` | `session.title` | `session.store` | `none` | 服务自身无外部副作用 |
| `lca.plugins.session.title_llm_provider` | `session.title.provider` | `session.title` | `network` | LLM 远端调用;经 `ctx.soft_get("llm")` 软查,缺席时 generate 上抛由服务 contained |

两插件均为 `L2 / PROVIDER / G3_FACTS`;provider 插件不 import 服务插件符号,
只经 `session.title` capability 注册(AGENTS.md §4 插件间禁止直接 import)。

## 6. 验证

```sh
uv run pytest tests/contracts/test_session_title_event.py \
  tests/plugins/session/test_title_service.py \
  tests/plugins/session/test_title_llm_provider.py -q
uv run pytest tests/contracts/ -q   # 词表追加不破坏既有注册
uv run ruff check lca/plugins/session/title_service lca/plugins/session/title_llm_provider
./scripts/lca-ops audit-plugin-shape
```

## 7. delete / 兼容条件

- 纯加法变更:无旧入口、无双写、无 COMPAT 窗口。
- 删除条件(若标题家族整体退役):移除两个插件目录 + `events.py` 的
  `SessionTitle` 注册 + 三个测试文件;检测命令
  `rg "session.title.v1" lca/ tests/` 仅剩本 ADR 与文档引用。
- `docs/adr/README.md` 索引行由主会话统一接入(本 PR 不动索引)。
