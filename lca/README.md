# LCA — Layered Cognitive Agent

> **平台目录宪法：** [docs/specs/platform-directory-architecture.md](../docs/specs/platform-directory-architecture.md)  
> **架构决策：** [docs/adr/0195-platform-architecture-convergence.md](../docs/adr/0195-platform-architecture-convergence.md)

## 是什么

LCA 是**插件化认知 Agent 框架**：Profile 编译成图，Graph 驱动 Loop，Loop 追加 Session 事实，Cognition 只算不写。

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
