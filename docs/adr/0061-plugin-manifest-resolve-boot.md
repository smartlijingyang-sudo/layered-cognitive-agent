# ADR-0061: 声明式插件 Manifest —— Resolve / Boot 两阶段与可验证依赖图

## 状态

Accepted

Amends: [ADR-0056](0056-plugin-group-contribution.md)（补齐未完成的 boot / 依赖声明路径；**不**撤回群服务投稿模型）

Amends: [ADR-0004](0004-protocol-first-pluggability.md)、[ADR-0005](0005-composition-root-l4.md)

## 背景

[ADR-0056](0056-plugin-group-contribution.md) 已确立：感知 / 判决向群服务 `add()`，L4 入口是 `spawn_*`，配置是装箱单。仍缺的是**可验证的加载模型**：`boot_entries` 按 YAML 文本序 `await setup`，YAML `inject` 与 `@plugin(requires=...)` 不参与激活，`requires` 与真实 `ctx.inject` 无统一校验，patch 为原地浅合并，环境变量可读散落在插件内。

插件体系的目的不是动态 import，而是把可替换运行时能力表示成可声明、可验证、可装配、可诊断的依赖图。

## 决定

### 1. Resolve 先于 Boot

公开入口：`resolve_profile()` → 不可变 `ResolvedProfile`；`boot_resolved_profile(resolved)` → 已启动 scope。`boot_profile()` 兼容门面，顺序调用二者。

| 阶段 | 做 | 禁止 |
|---|---|---|
| Resolve | 展开 bundle、深合并 patch、import `$module`、校验 Manifest / Config / DAG / 层级、解析 `{from_env}` | 业务对象、网络、静默回退 |
| Boot | 按 DAG 拓扑调用受限 `PluginContext.setup`；失败逆序 dispose | 改 resolved config、声明外 provide/require |
| Run | 只消费已启动 capability | 读未解析 YAML、模块级 fallback |
| Dispose | 逆拓扑释放，汇总清理异常 | 吞没清理错误 |

### 2. 一个插件一个 Manifest 身份

插件 ID 是配置、代码、诊断、测试的主键。Profile 条目 `id` 必须等于模块 `@plugin(id=...)`。`$module` 是唯一定位符。YAML `inject` 与装饰器 `name` 不再作为依赖事实源（迁移期可读，不写入新条目）。

必填字段：`id`、`Config`（可空模型，`extra="forbid"`）、`provides`、`requires`、`implements`、`layer`（`L0`–`L4`）、`kind`、`effects`、`test_suite`。

`kind`：`seam` | `provider` | `primitive` | `composite` | `driver` | `bridge`。群服务 Definition（`perceive` / `gates`）属 `seam`；向其 `add()` 的投稿属 `primitive`。组合只沿 capability 图进行（[ADR-0056](0056-plugin-group-contribution.md)）：禁止再引入 `gate.workspace-agent` 这类名单式 composite。

### 3. Capability 是 contracts 命名原语

公开交互经 `Capability[T]`（稳定字符串 key）。`PluginContext` 只暴露：`provide` / `require` / `register` / `emit`。实际交互键必须 ⊆ Manifest 声明（不变量 P1）。

### 4. DAG 由 provides → requires 推导

拓扑序只由 `requires` 决定；无路径并列项保持 profile 稳定顺序。拒绝：重复 ID、ID≠模块声明、未知配置字段、重复单例 provider、循环依赖、未满足 requires、未声明交互、逆向分层边、已启动树上的隐式 standard fallback。

业务顺序（sensor `order`、gate `slot`/`order`）仍属群服务契约，不借用 boot 序。

### 5. 配置是数据；秘密是引用

优先级：`bundle → profile patch → 受控 runtime override`。深合并、不可变、可追溯来源。密钥仅经 `{from_env: NAME, required?: bool}` 在 resolve 末端解析为 `SecretStr`；插件不得自行 `os.environ` 读凭证（不变量 P3）。dump / BootReport / 日志永不含明文秘密。

### 6. 与 ADR-0056 的分工

| 关切 | 归属 |
|---|---|
| Sensor / Gate 如何进入运行时 | 群服务 `add` / `assemble`（0056） |
| 谁先启动、缺依赖如何失败 | Manifest DAG + Resolve（本 ADR） |
| 装箱单（启用了谁） | Profile / Bundle / Patch |
| 对象图闭合 | `spawn_agent` / `spawn_team`（0056 / 0005） |

「签名即依赖」仍是方向；本 ADR 以 Manifest `requires`/`provides` 为**当前唯一强制**依赖事实源。签名派生可作为后续从 Manifest 生成的校验，不另开第三套 PrimitiveManifest schema。

## 放弃的方案

- 仅靠 YAML 文本序与手填 `inject` 表达依赖
- 插件内直接读环境变量展开密钥
- 自动扫描 / import side-effect 注册
- 全局 Service Locator 与「缺失则 new 标准实现」旁路
- 用大而全领域插件捆绑多个变化轴
- 撤回群服务投稿、恢复 Composer 点名 `sensor.*` / `gate.*`

## 后果

- 关插件 → Resolve 报出反向依赖链；运行时不再偷建实现
- `inspect-tree` / `why` / `dump-profile` / `graph` 回答：启了谁、配置从哪来、谁提供/消费、为何此序
- 每个生产插件可从文件顶部 Manifest 读到依赖与 `test_suite`
- 代价：resolver 承担静态校验与回滚；一行 `provide` 的 Definition 也要完整 Manifest

## 相关

- 实现入口：`lca/harness/plugin_api.py`、`lca/harness/profile/resolve.py`、`lca/harness/profile/boot.py`
- Capability：`lca/contracts/capabilities.py`
- 群服务：`lca/cognition/{perceive,gate}_service.py`
