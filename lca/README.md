# LCA — Layered Cognitive Agent

> **平台目录宪法：** [docs/specs/platform-directory-architecture.md](../docs/specs/platform-directory-architecture.md)  
> **架构决策：** [docs/adr/0195-platform-architecture-convergence.md](../docs/adr/0195-platform-architecture-convergence.md)

## 是什么

LCA 是**插件化认知 Agent 框架**：Profile 编译成图，Graph 驱动 Loop，Loop 追加 Session 事实，Cognition 只算不写。

## 1. 职责

LCA 是**插件化认知 Agent 框架**：Profile 编译成图，Graph 驱动 Loop，Loop 追加
Session 事实，Cognition 只算不写。本包按单向依赖层组织
（`contracts → infrastructure → cognition → runtime → agent`，`application` 为组合根，
`harness` 承载 Session/Profile/Boot 与声明式阶段，`plugins` 提供 Seam/Provider/
Loop Driver，transport plugin 独立于认知与运行层）。

## 2. 不负责

- G0 启动与事件 yaml SSOT：那是与 `lca` 平级的 `lca_kernel/`，下层不得 import 其内部
- 具体 provider 实现的业务语义：各层 README 自述职责与副作用，本文件只给地图
- 前端与沙箱连接器（`lobehub-ui/`、daemon）

## 3. 输入

包初始化期只接受 `lca.contracts` 的值类型：`lca/__init__.py` 静态 import
`lca.contracts.models.team.team.coordination` 与
`lca.contracts.protocols.journal.spec.spec`，加上标准库 `importlib` / `typing`。

## 4. 输出

`__all__` 声明的 `Agent` / `Team` / `TeamLead` 门面符号与 coordination 值类型
（`Debate`、`FanOut`、`Graph`、`Pipeline`、`PeerRelay`、`PeerSwarm`、
`LeadMandate`、`Governance`、`AgentSpec`、`LeadSpec`、`TeamSpec` …）。
其中 `Agent` / `Team` / `TeamLead` 三个名字由 `__getattr__` **按需**解析，
import 本包不等于装配组合根。

## 5. 允许依赖

- `lca.contracts`（静态）
- `lca.application.api.api`——仅经 `_LAZY_COMPOSITION_SYMBOLS` 白名单、仅这三个符号、
  仅在首次属性访问时 `import_module`

## 6. 禁止依赖

- 在包初始化期 import `application` / `runtime` / `agent` / `plugins`：那会把组合根
  变成 package import 的反向依赖边（AGENTS.md §2.1 单向层）
- 用本包门面做分层内部依赖：层内代码 import 具体子模块，门面只给外部调用方
- 借 `__getattr__` 兜底任意名字：白名单之外的名字必须失败

## 8. 失败语义

`from lca import X`（X 不在白名单）→ `AttributeError: module 'lca' has no
attribute 'X'`，不猜测、不静默返回 `None`。白名单符号的真实解析错误由
`lca.application.api.api` 自身抛出并向上传播（本层不吞异常）。首次成功解析后结果
写回 `globals()`，后续访问不再走 import。

## 9. 公共入口

```python
from lca import Agent, Team            # 外部调用方的简洁门面
from lca.contracts... import Decision   # 分层内部走具体子模块
```

## 7. 副作用

包级**无**：`import lca` 与 `lca/__init__.py` 不打开文件、不建连接、不写状态；
它只重导出 `contracts` 值类型，并按需解析 `Agent` / `Team` 门面。
真实的对外后果逐层记录在各包 README 的 §7：`lca/loop`（经 `Session.append` 落事实）、
`lca/session`（append-only 日志 + observer contained）、
`lca/infrastructure/observability`（sink 落盘、exporter 外发）、
`lca/plugins/transport`（carrier 追加终态事实、read 写诊断文件）。

## 顶层包地图

```text
lca/
├── contracts/       类型与 Protocol（无行为、无 I/O）
├── harness/         编译、MTK、plugin API
│   ├── graph/         图内核（目标 MTK 子包）
│   └── composition/   Profile → CompiledRunPlan
├── loop/            Agent loop 机制 + FactGateway（人读入口）
├── session/         事实 append / fold / repair（提升中）
├── cognition/       纯认知原语（零 emit）
├── runtime/         CognitiveRuntime 窄入口
├── agent/           AgentUnit / Team
├── application/     L4 组合根
├── infrastructure/  适配器与端口
└── plugins/         可替换 Manifest 贡献（见 plugins/ARCHITECTURE.md）

lca_kernel/          G0 启动 + 事件 yaml SSOT（与 lca 平级）
```

## 依赖方向（单向）

```text
contracts → infrastructure → cognition → runtime → agent → application
harness → contracts
loop / session → contracts, harness
plugins → contracts（经 Context 注入，禁止 plugin→plugin）
```

## 三时态

| 时态 | 问什么 | 去哪读 |
|---|---|---|
| Compile | 装什么？ | `bundles/` · `lca_kernel/boot.py` |
| Run | 这一步做什么？ | `lca/loop/README.md` |
| Observe | 发生了什么？ | `lca/session/` · `docs/observability/` |

## 人读入口（45 分钟全链路）

1. [lca_kernel/README.md](../lca_kernel/README.md) — 启动  
2. [lca/loop/README.md](loop/README.md) — 认知循环  
3. [lca/plugins/transport/README.md](plugins/transport/README.md) — HTTP  
4. [docs/observability/platform-readme.md](../docs/observability/platform-readme.md) — 观测链  
5. [lca/plugins/ARCHITECTURE.md](plugins/ARCHITECTURE.md) — 插件 seam 树  

## 验证

```bash
uv run python scripts/check_platform_directory.py
./scripts/lca-ops audit-plugin-shape
```

## 版本

schema_version: 3.0.0（目录架构 P0，2026-09-06）
