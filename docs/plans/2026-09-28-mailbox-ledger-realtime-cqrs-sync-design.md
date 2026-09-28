# Design Document: Agent Mail Hub 实时台账与异步 CQRS 投影引擎

## 1. 业务背景与问题定义

用户需要对 `smartlijingyangs.top` 域名邮箱的分配与验证码调用流水实现**实时、优雅、规范且具备生产级性能的台账更新**。

当前现状：
- 核心服务 `agent-mail-hub`（运行于 `0.0.0.0:8095`，公网经 Cloudflare Tunnel 由 `https://muse.smartlijingyangs.top/api/mailbox` 反向代理）在收到 `/api/mailbox/acquire` 与 `/api/mailbox/code` 时，只更新本地状态 `data/mail_pool.json` 并输出 `server.log`。
- 知识库归档文档 `smartlijingyang-mail-registry-record.md`（位于 `/home/lichao/everything-library/data/items/accounts-sop/`）此前由人工或 Agent 阶段性整理提交，无法随外部调用自动实时刷新。

直接在 API 主线程中同步修改 Markdown 存在严重弊端（I/O 阻塞延迟、并发截断损坏、耦合知识库格式）。因此必须采用生产级 CQRS 读写分离与事件驱动投影架构。

---

## 2. 架构设计与核心组件

### 2.1 整体架构图 (CQRS Event Sourcing + Debounced Projection)

```
[外部 Agent / 自动化注册流程]
             │
             ▼
   HTTP API (/acquire 或 /code)
             │
      ┌──────┴───────────────────────────────────┐
      ▼                                          ▼
[核心业务状态更新]                         [非阻塞事件派发]
更新 mail_pool.json                 写入 data/audit_events.jsonl (O(1) 追加)
                                                 │
                                                 ▼
                                        [asyncio.Queue 事件总线]
                                                 │
                                                 ▼
                                    ┌────────────────────────────┐
                                    │    LedgerProjector 投影器   │
                                    │  • 1.5s 消抖合并处理       │
                                    │  • 结构化模板确定性渲染     │
                                    │  • .tmp -> os.replace 原子写│
                                    │  • 非阻塞异步 Git Commit 队列│
                                    └────────────┬───────────────┘
                                                 │
                                                 ▼
                          [smartlijingyang-mail-registry-record.md]
                                                 │
                                                 ▼
                          [Everything Library 自动感知与网页呈现]
```

### 2.2 核心模块职责划分

1. **事件流核心 (`events.py`)**：
   - 定义不可变事件 DTO：`MailboxAcquiredEvent`、`CodeExtractedEvent`。
   - 维护持久化事件日志 `data/audit_events.jsonl`，所有写入均为原子追加（Append-only），执行耗时 < 0.1ms。

2. **台账投影引擎 (`projector.py`)**：
   - **消抖与批处理 (Debouncing)**：窗口设为 1.5 秒。连续事件到达时合并一次性渲染，消除高频磁盘抖动。
   - **确定性模板渲染 (Deterministic Markdown Renderer)**：读取最新 `mail_pool.json` 与 `audit_events.jsonl`，生成规范的 Frontmatter、调用流水表格、邮箱池资产总表与调用示例。
   - **原子文件替换 (Atomic Write)**：写入 `.tmp` 临时文件后通过 `os.replace` 原子替换，规避并发读写损坏。
   - **异步 Git 提交器 (Async Git Committer)**：独立的低优先级后台任务，消抖后（如最后一次事件产生后 10 秒）安全执行 `git add` 与 `git commit`，若遇到 git 锁冲突或异常自动重试或静默跳过，绝不阻塞主服务。

3. **API 服务集成 (`server.py`)**：
   - 在 FastAPI 生命周期 `lifespan` 中管理 `LedgerProjector` 的启动与优雅停机。
   - 在 `/api/mailbox/acquire` 与 `/api/mailbox/code` 成功后，仅向队列推入事件，请求延迟 0 增加。

---

## 3. 边界声明 (AP-01)

- **Owns (负责修改/交付)**:
  - `/home/lichao/agent-mail-hub/events.py`（新增：事件模型与持久化追加器）
  - `/home/lichao/agent-mail-hub/projector.py`（新增：消抖投影器与原子更新引擎）
  - `/home/lichao/agent-mail-hub/server.py`（修改：挂载投影器与非阻塞事件发射）
  - `/home/lichao/agent-mail-hub/tests/`（新增：单元与契约测试集）
  - `/home/lichao/everything-library/data/items/accounts-sop/smartlijingyang-mail-registry-record.md`（投影目标）
- **Does NOT own (严格禁止跨越)**:
  - 禁止改动 `everything-library/app/` 核心后端代码。
  - 禁止改动 `tools/muse-mcp-hub/` 代理端点。
  - 禁止改动远程 Cloudflare Worker 脚本。

---

## 4. 架构不变量与测试验证 (AP-02)

1. **不变量 1：事件追加只读与不可变性**
   - 验证：多次调用仅追加 `audit_events.jsonl`，历史行哈希不变。
2. **不变量 2：API 延迟零阻塞**
   - 验证：事件推入仅耗时 < 1ms，投影过程完全运行在后台任务中。
3. **不变量 3：投影渲染幂等性**
   - 验证：相同的数据源（`mail_pool.json` + `audit_events.jsonl`）多次执行渲染，产生的 Markdown 产物 100% 字节一致。
4. **不变量 4：原子写与文件完整性**
   - 验证：在并发模拟触发渲染时，文件在任何时刻均为合法的 UTF-8 Markdown，绝无 0 字节截断。
5. **不变量 5：故障完全隔离**
   - 验证：当 Markdown 目标路径不可写或只读时，API `/acquire` 与 `/code` 仍返回 HTTP 200 正常响应。

---

## 5. 自治与爆炸半径分级 (AP-05)

- **等级**: `AUTOPILOT`（局限于 `agent-mail-hub` 微服务与目标知识库文件，已具备完备单测与平滑重启机制）。
