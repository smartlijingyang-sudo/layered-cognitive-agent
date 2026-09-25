# Agent-Friendly 动态深度搜索与研究智能体实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 构建一个基于 TypeSafe Jev/Laya 概率决策与动态能力池无界协同的 Agent-Friendly 深度搜索与研究智能体系统，支持秒级快答到多源深搜的自适应执行。

**Architecture:** 动态能力池注册中心（CapabilityRegistry）提供自描述工具定义；LLM 语义发散结合 TypeSafe Jev/Laya 概率收敛（IntentRouter）实现连续深度与工具集动态裁剪；自适应引擎（FederatedSearchEngine）按深度分级执行并语义重排；最终通过独立 CLI（`search-agent`）及 RESTful 端点提供机器友好的 JSON/流式双轨支持。

**Tech Stack:** Python 3.11+, TypeSafe SDK (`typesafe_sdk`, jev-latest/laya), FastAPI, HTTPX, SQLite FTS5, SearXNG, GitHub CLI (`gh`), Grok API, pytest.

---

### Task 1: 动态能力注册中心 (Capability Registry)

**Files:**
- Create: `/home/lichao/everything-library/app/search/capabilities.py`
- Test: `/home/lichao/everything-library/tests/test_capabilities.py`
- Does NOT own: `app/storage/*`, `app/web/*`, `~/layered-cognitive-agent/src/*` (AP-01)
- Invariants to test:
  1. 所有注册能力必须包含合法的 `id`, `name`, `category`, `latency_tier`, `description`；
  2. 支持动态注册、注销和按类别过滤能力列表；
  3. `get_available_capabilities()` 只返回当前系统可用的能力集合 (AP-02)。

**Step 1: Write the failing test**
编写 `tests/test_capabilities.py`，验证能力注册、元数据结构与可用性过滤。

**Step 2: Run test to verify it fails**
运行: `pytest tests/test_capabilities.py -v`（在 `/home/lichao/everything-library` 目录下）
预期: FAIL（`ModuleNotFoundError: No module named 'app.search.capabilities'`）

**Step 3: Write minimal implementation**
创建 `app/search/capabilities.py`，实现 `SearchCapability` 数据类与 `CapabilityRegistry` 动态单例容器，预置 `searxng_web`, `jina_reader`, `grok_x_search`, `grok_web_search`, `github_cli`, `community_forum`, `local_everything` 等自描述能力。

**Step 4: Run test to verify it passes**
运行: `pytest tests/test_capabilities.py -v`
预期: PASS

**Step 5: Commit**
```bash
cd /home/lichao/everything-library
git add app/search/capabilities.py tests/test_capabilities.py
git commit -m "feat(search): implement dynamic capability registry"
```

---

### Task 2: Jev/Laya 意图分析与动态路由器 (IntentRouter)

**Files:**
- Create: `/home/lichao/everything-library/app/search/intent_router.py`
- Test: `/home/lichao/everything-library/tests/test_intent_router.py`
- Does NOT own: `app/auth.py`, `app/storage/md_store.py` (AP-01)
- Invariants to test:
  1. 鲁棒性不变式：在无 `TYPESAFE_API_KEY` 或 TypeSafe 接口超时抛出异常时，50ms 内平滑降级至本地启发式规则，绝对不崩溃 (AP-02)；
  2. 智能裁剪不变式：对于非代码/娱乐类问题（如“美国电影推荐”），门控决策必须将 `github_cli` 概率打分降至阈值以下，避免误调 (AP-02)；
  3. 输出结构不变式：返回对象必须包含 `depth_level` (1~5), `urgency`, `selected_capabilities`, `confidence`, `rationale`。

**Step 1: Write the failing test**
编写 `tests/test_intent_router.py`，覆盖 Jev/Laya SDK 模拟调用、无 Key 优雅降级、连续打分（1~5）及针对特定语义的问题工具集智能裁剪测试。

**Step 2: Run test to verify it fails**
运行: `pytest tests/test_intent_router.py -v`
预期: FAIL（`ModuleNotFoundError: No module named 'app.search.intent_router'`）

**Step 3: Write minimal implementation**
创建 `app/search/intent_router.py`，基于 `typesafe_sdk` 构建双系统协同路由逻辑：
- 提取用户语义；
- 动态获取候选能力池；
- 调用 TypeSafe `Score` 原语评估连续调研深度（1~5）；
- 调用 `Questions` 并行评估各能力在当前问题下的相关度；
- 实现优雅超时与错误降级处理器。

**Step 4: Run test to verify it passes**
运行: `pytest tests/test_intent_router.py -v`
预期: PASS

**Step 5: Commit**
```bash
cd /home/lichao/everything-library
git add app/search/intent_router.py tests/test_intent_router.py
git commit -m "feat(search): implement typesafe jev dynamic intent router"
```

---

### Task 3: 引擎自适应执行与阻塞式 API 端点扩展

**Files:**
- Modify: `/home/lichao/everything-library/app/search/engine.py`
- Modify: `/home/lichao/everything-library/app/api/routes.py`
- Test: `/home/lichao/everything-library/tests/test_engine_adaptive.py`
- Does NOT own: `app/web/*` (AP-01)
- Invariants to test:
  1. `execute_search(query)` 同步/异步接口返回统一标准字典格式（含 `query`, `depth_level`, `selected_capabilities`, `sources`, `answer`）；
  2. `depth_level <= 2` 时走极速路径（< 1.5s），跳过复杂的 3 Worker 深度拆解；
  3. `POST /api/search/query` 端点在携带有效认证（或本地放行）时能够一次性返回完整 JSON。

**Step 1: Write the failing test**
编写 `tests/test_engine_adaptive.py`，验证自适应引擎的深度分支执行与 RESTful `/api/search/query` 返回结构。

**Step 2: Run test to verify it fails**
运行: `pytest tests/test_engine_adaptive.py -v`
预期: FAIL

**Step 3: Write minimal implementation**
- 在 `app/search/engine.py` 中引入 `IntentRouter` 与 `CapabilityRegistry`；
- 封装 `execute_adaptive_search` 与支持快搜直出的执行流水线；
- 在 `app/api/routes.py` 中新增 `POST /api/search/query` 阻塞端点，并在现存 `stream_federated_search` 开头注入 Jev 意图分析事件。

**Step 4: Run test to verify it passes**
运行: `pytest tests/test_engine_adaptive.py -v`
预期: PASS

**Step 5: Commit**
```bash
cd /home/lichao/everything-library
git add app/search/engine.py app/api/routes.py tests/test_engine_adaptive.py
git commit -m "feat(search): add adaptive depth execution and agent query endpoint"
```

---

### Task 4: Agent-Friendly CLI 客户端 (search-agent)

**Files:**
- Create: `/home/lichao/everything-library/bin/search-agent`
- Test: `/home/lichao/everything-library/tests/test_cli_agent.py`
- Does NOT own: `~/everything-library/data/items/*` (AP-01)
- Invariants to test:
  1. CLI 在接收 `--json` 参数时，标准输出必须是合法 JSON，且包含核心结果字段；
  2. 调试和进度日志严格写入 `stderr`，不得污染 `stdout`；
  3. 正常退出码为 0，异常退出码非 0。

**Step 1: Write the failing test**
编写 `tests/test_cli_agent.py`，使用 `subprocess` 触发 `bin/search-agent`，验证 `--json` 输出合法性、退出码与 `--fast`/`--deep` 参数透传。

**Step 2: Run test to verify it fails**
运行: `pytest tests/test_cli_agent.py -v`
预期: FAIL（`FileNotFoundError: bin/search-agent`）

**Step 3: Write minimal implementation**
创建 `bin/search-agent`：
- Python 脚本执行器，支持命令行参数解析；
- 能够直连本地 `FederatedSearchEngine` 或通过 HTTP 调用本地服务；
- 输出模式：默认终端 Markdown 排版；`--json` 输出纯结构化数据。
- 赋予执行权限 `chmod +x bin/search-agent`。

**Step 4: Run test to verify it passes**
运行: `pytest tests/test_cli_agent.py -v`
预期: PASS

**Step 5: Commit**
```bash
cd /home/lichao/everything-library
git add bin/search-agent tests/test_cli_agent.py
git commit -m "feat(cli): add agent-friendly search-agent CLI"
```

---

### Task 5: 全链路端到端实测与验收验证

**Files:**
- Verify: 全套自动化测试
- Verify: 真实实机搜索命令运行（快查测试 + 电影多源深搜测试）
- Modify: `docs/plans/task.md`
- Invariants to test:
  1. 全量 pytest 测试套件 100% 通过；
  2. 实测 `search-agent "Python 3.12 GIL release" --json` 能够秒级返回；
  3. 实测 `search-agent "最近好看的美国电影"` 能够并发多源返回高质量研报。

**Step 1: 运行全量测试**
运行: `pytest tests/ -v`

**Step 2: 实操验证 CLI 与 JSON 格式**
运行: `bin/search-agent "2026年最近好看的美国电影" --json`

**Step 3: 更新任务追踪看板**
在 `docs/plans/task.md` 记录实施成果与证据。
