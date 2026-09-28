# Agent Mail Hub 实时台账与异步 CQRS 投影引擎 Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 构建生产级异步 CQRS 读写分离事件流与消抖投影引擎，实现 `smartlijingyangs.top` 邮箱分配与验证码调用时，知识库 Markdown 台账毫秒级/近实时原子更新并自动异步纳入 Git 跟踪，同时对 API 请求延迟与可用性 0 负面影响。

**Architecture:** CQRS 模式。API 处理请求时仅执行核心逻辑并向内部追加写不可变事件流 `audit_events.jsonl`（耗时 <0.1ms）；事件推入非阻塞 `asyncio.Queue`；后台 `LedgerProjector` 消抖 1.5 秒后读取 SSOT 状态并确定性渲染 Markdown，利用 `.tmp` + `os.replace` 保证原子落盘；随后触发轻量级异步 Git 提交队列，全流程异常安全隔离。

**Tech Stack:** Python 3.12, FastAPI, Pydantic, asyncio, Uvicorn, pytest, Git.

---

### Task 1: 事件模型与持久化追加器 (events.py)

**Files:**
- Create: `/home/lichao/agent-mail-hub/events.py`
- Create: `/home/lichao/agent-mail-hub/tests/test_events.py`
- Does NOT own: `/home/lichao/agent-mail-hub/server.py`, `everything-library/` (AP-01)
- Invariants to test:
  1. 不可变事件序列化合规，字段强校验（Pydantic BaseModel）。
  2. 原子追加写入 `data/audit_events.jsonl`，执行耗时 < 1ms，且多线程/并发下行完整（AP-02）。
  3. `load_recent_events` 能够正确倒序或正序加载历史事件。

---

### Task 2: 台账投影器与消抖原子落盘 (projector.py)

**Files:**
- Create: `/home/lichao/agent-mail-hub/projector.py`
- Create: `/home/lichao/agent-mail-hub/tests/test_projector.py`
- Does NOT own: `/home/lichao/agent-mail-hub/server.py`, `muse-mcp-hub/` (AP-01)
- Invariants to test:
  1. 幂等性：给定相同的 `mail_pool.json` 与 `audit_events.jsonl`，多次调用 `render_markdown()` 输出 100% 一致。
  2. 原子落盘安全：写入先经 `.tmp` 临时文件，再经 `os.replace` 原子替换，测试中断或读取绝无 0 字节损坏。
  3. 异常隔离：目标路径不存在或无写权限时，捕获异常打日志，不向上传播致命错误。

---

### Task 3: 异步 Git 自动提交模块与消抖控制

**Files:**
- Modify: `/home/lichao/agent-mail-hub/projector.py`
- Modify: `/home/lichao/agent-mail-hub/tests/test_projector.py`
- Does NOT own: `everything-library/app/` (AP-01)
- Invariants to test:
  1. Git Commit 消抖：连续触发多次写操作，只在静默期（如 5 秒）后执行一次 commit，防止 Git 碎片化。
  2. Git 异常弹性：若存在 `.git/index.lock` 或无改动，优雅跳过，绝不阻塞投影循环。

---

### Task 4: API 服务集成与生命周期挂载 (server.py)

**Files:**
- Modify: `/home/lichao/agent-mail-hub/server.py`
- Create: `/home/lichao/agent-mail-hub/tests/test_server_integration.py`
- Does NOT own: `everything-library/` (AP-01)
- Invariants to test:
  1. `/api/mailbox/acquire` 成功后，自动发射 `MailboxAcquiredEvent` 并推入 Queue。
  2. `/api/mailbox/code` 成功提取验证码后，自动发射 `CodeExtractedEvent` 并推入 Queue。
  3. 接口响应耗时与改造前无明显差异（发射耗时 < 1ms）。

---

### Task 5: 回填今日实战历史数据、平滑重启与实测闭环

**Files:**
- Update: `/home/lichao/agent-mail-hub/data/audit_events.jsonl`
- Update: `/home/lichao/everything-library/data/items/accounts-sop/smartlijingyang-mail-registry-record.md`
- Verify: 重启 `:8095` 服务并调用 live API 验证端到端投影与 Git 自动提交。
