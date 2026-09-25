# Agent-Friendly 动态深度搜索与研究智能体系统设计文档

> **创建日期:** 2026-09-25  
> **设计状态:** 已确认（User Approved）  
> **Autopilot 级别:** DRAFT  

---

## 1. 业务目标与第一性原理

### 1.1 业务愿景
打造一个**全自主、全信息源、兼具极速快查与深度立体调研的 Agent-Friendly 搜索智能体**。
系统能够替代用户在互联网各个角落进行手动搜索与拼凑，无论用户输入的是简短事实查询，还是复杂的开放性调研（如“搜索最近好看的美国电影，附带多方评价与观看下载线索”），系统都能自主感知意图、自适应调配工具链、多源交叉印证，并最终输出高价值、高密度的事实研报。

### 1.2 核心第一性原理：双系统无界协同（System 1 + System 2）
- **杜绝硬编码与死板枚举**：现实世界的搜索意图与工具生态千变万化，不能用静态写死的 `if-else` 或固定三选一选项限制决策。
- **发挥 LLM（System 2）的发散与综合优势**：大模型（Qwen 3.8 Max / Grok）负责对用户复杂、模糊的自然语言进行开放式语义理解，推演动态搜索维度与定制化 Queries，并在终点执行多源长文交叉终审。
- **发挥 Jev / Laya（System 1）的概率收敛与毫秒决策优势**：TypeSafe System One 模型（`jev-latest` / `laya`）负责在微秒到毫秒级内，对动态能力池打出严格的概率分值（Continuous Score / Noul），进行置信度门控与候选结果语义重排（Re-ranking），杜绝慢吞吞的幻觉式 Prompt 决策。
- **Agent-Friendly First**：对外暴露标准化 CLI（`--json`）、RESTful 同步/流式端点，以及标准 MCP/函数接口，让上层 AI Agent（如 LCA、Claude、Antigravity、OpenCode）能够像调用系统内置函数一样直接使用。

---

## 2. 边界规范（Boundaries）

- **Owns（本方案构建与修改）**：
  1. `app/search/capabilities.py`：动态能力注册中心（Dynamic Capability Registry），包含自描述元数据（名称、领域标签、延迟分级、查询模板、适配器接口）。
  2. `app/search/intent_router.py`：双系统协同意图路由器（LLM 动态维度发散 + TypeSafe Jev/Laya 概率打分与置信度门控，带无 Key/网络超时优雅降级）。
  3. `app/search/engine.py`：自适应执行引擎，支持从单点秒级快答（< 1.5s）到多源聚合（3~5s）再到全维深度研报（15~25s）的连续级调度。
  4. `bin/search-agent`：Agent-Friendly CLI 工具，支持 `--json`、`--fast`、`--deep`、`--stream` 等参数，标准 exit code 与 stdout/stderr 分流。
  5. `app/api/routes.py`：扩展支持 Agent 阻塞式 JSON 查询接口与 Web/SSE 流式感知。
  6. 确定性自动化测试套件：验证能力注册、路由评分、降级兜底及端到端输出格式。
- **Does NOT own（严格禁止越界）**：
  1. 不修改主工程 `~/layered-cognitive-agent` 内部核心运行时代码（保持单向调用或隔离）。
  2. 不修改已有的账号管理与密码认证核心。
  3. 不擅自引入未经许可的重量级非标准依赖，保持轻量高效。

---

## 3. 总体架构与数据流图

```text
                          ┌──────────────────────────────────────────────┐
                          │         调用入口 (Agent-Friendly 入口)        │
                          │  1. 终端 CLI: search-agent "query" [--json]  │
                          │  2. REST API: POST /api/search/query         │
                          │  3. Web / SSE: POST /api/search/federated    │
                          └──────────────────────┬───────────────────────┘
                                                 │
                                                 ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. 动态能力池（Dynamic Capability Registry: capabilities.py）                          │
│    • 工具自描述对象集合（id, name, tags, latency_tier, cost, query_builder）             │
│    • 覆盖：SearXNG、Jina Reader、Grok (x_search / web_search / open_page)、            │
│            GitHub CLI、Linux.do/Reddit 社区、Everything-Library 本地智库等             │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. 语义发散引擎（LLM System 2: Qwen / Grok）                                           │
│    • 动态理解输入语义，发散出 2~4 个最切合的探索维度与搜索指令（如口碑评分、实时推文、资源下载）│
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. 概率校准与决策中枢（TypeSafe Jev/Laya System 1: intent_router.py）                   │
│    • 动态载入候选能力上下文（State）                                                   │
│    • 【调研深度连续打分 (Score: 1~5)】：自适应匹配响应时效（1 档快答 -> 5 档深度调查）     │
│    • 【工具能力相关度评估 (Noul/Choice)】：毫秒级输出各能力有效性概率与置信度           │
│    • 【置信度门控与裁剪】：自动剔除不相关工具（如查电影自动剔除 GitHub 代码仓）          │
│    • 【降级机制】：网络不可达或未配 Key 时，毫秒级降级至本地轻量规则，永不报错中断         │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. 自适应调度执行与 Jev 语义重排（Adaptive Execution & Re-ranking）                     │
│    • 并发启动选中的工具链获取原始数据                                                  │
│    • 利用 Jev 极速对候选结果进行相关性打分与去噪（Re-ranking），保留高密度事实            │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 5. Master LLM 综合研报生成与 Agent-Friendly 输出                                       │
│    • 输出纯净 JSON（--json）给上层 Agent 解析；或输出排版精美的 Markdown 报告给用户       │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 关键模块详细设计

### 4.1 动态能力注册中心 (`app/search/capabilities.py`)
每个能力实现统一定义：
```python
@dataclass
class SearchCapability:
    id: str                         # e.g., "searxng_web", "grok_x_search", "github_cli", "jina_reader"
    name: str                       # 显示名称
    category: str                   # "web", "social", "code", "community", "local", "media"
    description: str                # 能力专长自描述
    latency_tier: str               # "instant" (<1s), "fast" (1-3s), "medium" (3-8s), "slow" (>8s)
    is_available: Callable[[], bool]# 运行时动态健康检查
```

### 4.2 Jev/Laya 意图与决策中枢 (`app/search/intent_router.py`)
- 利用 `typesafe_sdk.TypeSafeClient`：
  - 调用 `Score`: `depth_level`（1=快速单点事实，3=多源聚合比对，5=全网全维深度研报）；
  - 调用 `Questions`: 对当前活跃的能力池进行并发判定，获取工具选择概率；
  - 自动捕获 `TypeSafeError` / 超时，并无缝切到本地启发式备用逻辑（Heuristic Fallback）。

### 4.3 Agent-Friendly CLI (`bin/search-agent`)
- 提供便捷的命令行入口：
  - `search-agent "query"`：默认自动智能路由，终端输出 Markdown 研报。
  - `search-agent "query" --json`：标准输出仅包含纯净 JSON（所有调试日志重定向至 stderr），方便 LLM / 脚本通过子进程或反引号无损解析。
  - `search-agent "query" --fast` / `--deep`：允许强制覆盖决策深度。

---

## 5. 质量保证与自动化测试不变式（Invariants in Tests）

- **不变式 1（鲁棒性不变式）**：当 TypeSafe 服务或网络异常时，`IntentRouter` 必须在 50ms 内优雅降级，不得向上抛出未捕获异常。
- **不变式 2（工具裁剪不变式）**：对于明显非代码类查询（如“美国电影推荐”），相关度门控必须确保排除代码类工具（如 `github_cli`），避免无意义消耗。
- **不变式 3（输出契约不变式）**：在 `--json` 模式下，标准输出必须能够无缝通过 `json.loads()` 解析，且必须包含 `query`, `depth_level`, `selected_capabilities`, `sources`, `answer` 五大核心字段。
