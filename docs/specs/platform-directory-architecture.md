# Platform Directory Architecture

> **状态：** Proposed（ADR-0195 配套规格）  
> **权威决策：** [ADR-0195](../adr/0195-platform-architecture-convergence.md) · [ADR-0194](../adr/0194-cognitive-loop-architecture-convergence.md) · [package-organization-discipline.md](package-organization-discipline.md)

本文是 LCA **目录宪法**：每个顶层包、子包放什么、禁止什么、与插件 seam 如何对应。代码搬迁按本文「迁移态」列执行；**新代码默认走目标列**。

---

## 1. 第一性原理

| 原则 | 含义 |
|---|---|
| **目录 = 职责边界** | 不是文件堆；每个目录必须能用一个名词短语命名 |
| **机制 vs 原语 vs 插件** | G0 机制不可插件化；认知原语可替换；插件 = Manifest 声明的贡献 |
| **三时态分离** | compile（harness/kernel）· run（loop/cognition）· observe（session/fold/export） |
| **读写分离** | transport `carrier/` 写触发；`read/` 只 fold；session 只 append |
| **8/10/15** | 每目录直接 `.py` ≤8 正常，9–10 预警，>10 必拆，>15 阻断或 ADR 豁免 |

---

## 2. 仓库顶层

```text
layered-cognitive-agent/
├── lca/                    # 业务框架（五层 + loop + session）
├── lca_kernel/             # G0：启动 · plan · 事件机制 yaml
├── bundles/                # Profile 装配清单（配置 SSOT）
├── tests/                  # 测试（镜像 lca 结构）
├── docs/                   # adr · specs · design · observability
├── scripts/                # 门禁 · lca-ops
├── lobehub-ui/             # 前端（不直接改）
└── vendor/                 # vendored（不直接改）
```

**禁止**在根目录新增 `gateway/`（Transport 已在 `lca/plugins/transport/`）。

---

## 3. `lca/` 顶层包（目标 9 包）

| 包 | 环 | 职责 | 不负责 |
|---|---|---|---|
| [`contracts/`](../contracts/README.md) | R0 | Protocol、DTO、枚举、闭集 | 行为、I/O、env |
| [`harness/`](../harness/README.md) | R0 | 编译、MTK、Profile resolve、plugin API | 业务 cognition、HTTP |
| [`loop/`](../loop/README.md) | R1 | Turn 驱动、PhaseTransaction、FactGateway | Reasoner/Gate 算法 |
| [`session/`](../session/README.md) | R1 | append、fold、repair、checkpoint | 业务语义 |
| [`cognition/`](../cognition/README.md) | R2 | Brain/Body/Memory/Gate 纯算法 | Session/Journal/Spine emit |
| [`runtime/`](../runtime/README.md) | R1 | CognitiveRuntime 窄入口、bindings | phase 业务 |
| [`agent/`](../agent/README.md) | — | AgentUnit、Team 调度 | HTTP、Plan 编译 |
| [`application/`](../application/README.md) | L4 | 组合根、spawn、API 门面 | 认知原语实现 |
| [`infrastructure/`](../infrastructure/README.md) | — | 适配器、持久化端口、LLM 桥 | 业务 fold 策略 |
| [`plugins/`](../plugins/ARCHITECTURE.md) | R3 | 可替换 Manifest 贡献 | G0 机制、MTK |

依赖方向（单向）：`contracts → infrastructure → cognition → runtime → agent → application`；`harness` 仅依赖 `contracts`；`loop/session` 依赖 `contracts` + `harness`；`plugins` 经 Context 注入，禁止 plugin→plugin import。

---

## 4. `lca_kernel/`（G0，与 lca 平级）

见 [lca_kernel/README.md](../../lca_kernel/README.md)。

| 子目录/模块 | 职责 |
|---|---|
| `source.py` `resolve.py` | K1 Profile 解析 |
| `plan.py` | K2 Plan 编译 |
| `boot.py` `closure.py` | K3–K4 启动与闭包 |
| `observability.py` | K5 观测 registry 装配 |
| `lifecycle.py` `env.py` `hmr.py` | K6–K8 |
| `events/config/` | category / producer **yaml SSOT** |
| `events/bus.py` `fold.py` `payloads*.py` | EnvelopeBus、fold 原语 |

**禁止：** Starlette、transport、run 事实 append（boot catalog 除外）。

---

## 5. `lca/harness/` 子结构

| 子目录 | 现状 | 目标 | 职责 |
|---|---|---|---|
| `declarative/` | 有 | 拆分为下两行 | 声明式 phase graph |
| `graph/` | **新建** | MTK 核心 | 编译、验证、解释、traverse、governance |
| `composition/` | **新建** | profile/boot 编译 | resolve、assembler、plan_compiler |
| `profile/` | 有 | 收拢到 composition | Profile 源、boot projection |
| `plugin_api.py` 等 | 根 | 保留 | Plugin 装饰器、Manifest |
| `middleware/` | 有 | 保留 | COGNITIVE_PHASES seam 注册 |
| `session/` | 有 | 与 `lca/session` 合并 | harness 侧 session emit 契约 |
| `projection/` | 有 | 保留 | fold 契约（非 run 热路径写） |

**MTK 禁止：** 具体 plugin id、工具名、LLM 品牌字符串。

---

## 6. `lca/loop/` 子结构（目标）

| 路径 | 职责 |
|---|---|
| `README.md` | 人读入口 |
| `driver.py` | ← `runtime/declarative_runtime.py` |
| `transaction.py` | ← `harness/declarative/lifecycle/phase_transaction.py` |
| `fact_gateway.py` | 唯一事实生产门面（G0 语义） |
| `phases/` | PhaseExecutor **注册表读模型**（非实现） |
| `control/` | 控制 contribution 契约 |

实现仍在 `plugins/loop/` 直至 P4 搬迁完成。

---

## 7. `lca/session/` 子结构（目标）

| 路径 | 职责 | 迁移自 |
|---|---|---|
| `append.py` | Session.append 公共 API | `plugins/session/runtime/session.py` |
| `catalog.py` | `@session_event` 词表 | `plugins/session/runtime/event_catalog.py` |
| `fold.py` | 纯 fold 入口 | `lca_kernel/events/fold.py` 再导出 |
| `repair.py` | crash turn repair | `plugins/session/runtime/repair.py` |
| `checkpoint.py` | 三边界 policy | `plugins/session/checkpoint_policy/` |
| `bind.py` | run bind / spine hook | `plugins/session/runtime/bind.py` |

**SSOT：** durable = `<run_id>.spine.jsonl`；in-process = `Session` 实例。

---

## 8. `lca/cognition/` 子结构（v3 概念群）

| 子目录 | 概念群 | 职责 | 禁止 |
|---|---|---|---|
| `perceive/` | Perceive | PerceiveHub、Sensor 实现 | Session.append |
| `brain/` | Think + Gate | Reasoner、Pipeline、decision_gates | spine_reflector |
| `body/` | Act | Body、SafeExecutor、tool dispatch | 绕过 CommandEnvelope |
| `memory/` | Memory | propose/commit 算法 | 直写 State |
| `sensors/` | Perceive | 世界读取传感器 | Reducer 写 |
| `collaboration/` | Collaboration | Team 认知辅助 | transport |

**Gate 不是独立目录级 phase**；`brain/decision_gates/` 是 Think 子链。

---

## 9. `lca/plugins/` — Seam 树（真正插件化的目标物理布局）

> 完整映射与 43 个 legacy 顶层目录对照见 [plugins/ARCHITECTURE.md](../plugins/ARCHITECTURE.md)。

```text
plugins/
├── ARCHITECTURE.md          # 本树 + legacy 对照 + 迁移状态
├── seams/                   # Seam 定义（Protocol 绑定声明，无 @plugin 业务）
│   perceive/ think/ act/ gate/ memory/ state/ journal/ observability/ collaboration/
├── cognitive/               # 可替换认知实现
│   perceive/<id>/plugin.py
│   think/<id>/plugin.py
│   brain/<id>/plugin.py
│   body/<id>/plugin.py
│   gate/<id>/plugin.py       # 薄注册 → cognition/brain/decision_gates
│   memory/<id>/plugin.py
│   reasoner/<id>/plugin.py
│   critic/<id>/plugin.py
│   sensors/<id>/plugin.py
├── loop/                    # 执行图相关插件
│   phase/<phase>/<variant>/plugin.py
│   control/<slot>/<id>/plugin.py
│   driver/<id>/plugin.py
│   reducer/<id>/plugin.py
├── observability/           # 观测链插件（仅 fold/export）
│   deriver/<id>/plugin.py
│   exporter/<id>/plugin.py
│   sink/<id>/plugin.py
│   provider/<seam>/<id>/plugin.py   # OTel/Langfuse 等
├── transport/               # 承运
│   webserver/carrier/ read/ wire/ doctor/
│   cli/                     # 后续
├── domain/                  # 产品域
│   assistant/<id>/
│   collaboration/<id>/
│   tools/<id>/
│   integrations/<id>/
│   skill/ learning/ ...
├── composition/             # 装配辅助
│   composer/ factories/ profile/ prompts/ roles/ bundles/
└── meta/                    # 注册表桥（尽量薄）
    providers/ strategies/ act/ state/
```

**一包一 plugin 规则：**

```text
plugins/<seam>/<group>/<plugin-id>/
  plugin.py      # 唯一 @plugin 入口
  config.py      # 可选
  tests/         # 或 tests/plugins/...
```

---

## 10. Legacy 顶层目录处置（43 → seam 树）

| Legacy 目录 | 目标 | 状态 |
|---|---|---|
| `phase_graph/` | `loop/phase/*` | 待迁 P4 |
| `control_contributions/` | `loop/control/*` | 待迁 P4 |
| `events/publishers/spine_reflector_*` | **删除** → FactGateway | 待迁 P2 |
| `session/` | `lca/session/` + 薄 plugin | 待迁 P4 |
| `observability/` | `observability/{deriver,exporter,sink,provider}/*` | 待迁 P2 |
| `brain/` `think/` `body/` `gate/` `gates/` | `cognitive/*` | 待迁 P4 |
| `transport/` | 保留，内分 carrier/read | 待迁 P3 |
| `composer/` `factories/` `profile/` | `composition/*` | 待迁 P4 |
| `assistant/` `tools/` `integrations/` | `domain/*` | 待迁 P4 |
| `seams/` | **保留**（seam 定义，非业务 plugin） | 稳定 |
| `loop_drivers/` | `loop/driver/*` | 待迁 P4 |
| `runtime/` (plugins) | `loop/reducer/*` | 待迁 P4 |

**迁移态模板（代码注释）：**

```text
# MIGRATION(owner: ADR-0195, from: lca.plugins.phase_graph.perceive,
#           to: lca.plugins.loop.phase.perceive.standard,
#           delete_when: bundles 全部改 $module 且 grep from 路径为 0)
```

---

## 11. `lca/infrastructure/` 子结构

| 子目录 | 职责 | 禁止 |
|---|---|---|
| `observability/` | 端口、adapter、**薄** spine 工具 | 业务 deriver、第二事实 write |
| `persistence/` | run buffer、fsync | Session 语义 |
| `session/` | **过渡** emit helper → 迁 `lca/session` | 长期保留 |
| `llm_adapter/` `openai_compat/` | LLM 桥 | 认知决策 |
| `sandbox/` `tools/` | 执行环境 | 绕过 Body |
| `cli/` | lca-ops 命令 | HTTP 路由 |

---

## 12. `lca/plugins/transport/webserver/` 目标

| 子目录 | 职责 |
|---|---|
| `server.py` `router.py` `lifespan_adapter.py` | ASGI 壳 |
| `carrier/runs/` | POST run、resume、answer |
| `carrier/assistants/` `carrier/composio/` | 域 API |
| `read/runs/` | live、timeline、debug、terminal 投影 |
| `wire/` | DTO |
| `doctor/` | 只读诊断 |

Legacy `handlers/runs/*` 在 P3 逐子域迁入上表。

---

## 13. 观测目录对照

| 段 | 目标位置 | Legacy |
|---|---|---|
| Registry | `lca_kernel/events/config/` | `infrastructure/.../manifest.py` |
| Gateway | `lca/loop/fact_gateway.py` | 134× emit_* |
| Session | `lca/session/` | `plugins/session/runtime/` |
| Deriver | `plugins/observability/deriver/*` | infra+plugins 双份 |
| Exporter | `plugins/observability/exporter/*` | `plugins/observability/*_provider.py` 根 |

见 [observability/platform-readme.md](../observability/platform-readme.md)。

---

## 14. 验证

```bash
# 目录门禁（P0）
uv run python scripts/check_platform_directory.py

# 架构测试
uv run pytest tests/architecture/test_platform_directory.py -q

# 插件形状
./scripts/lca-ops audit-plugin-shape

# 包规模
uv run python scripts/check_package_organization.py  # 若存在
```

---

## 15. 迁移波次（与 ADR-0195 §6 一致）

| 波 | 目录动作 |
|---|---|
| P0 | 本文 + 各 README + `check_platform_directory.py` |
| P1 | `lca/session/`、`lca/loop/fact_gateway.py` 落地 |
| P2 | `plugins/observability/{deriver,exporter}/` 开包；删 reflector |
| P3 | `transport/{carrier,read}/` |
| P4 | legacy 顶层 → seam 树；bundle `$module` 更新 |
| P5 | 删空 legacy 目录 + COMPAT shims |

---

## 16. 相关文档

- [ADR-0195 Platform Convergence](../adr/0195-platform-architecture-convergence.md)
- [plugins/ARCHITECTURE.md](../../lca/plugins/ARCHITECTURE.md)
- [declarative-phase-graph-spec.md](declarative-phase-graph-spec.md)
