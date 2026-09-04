# Agent Note: DeliveryQueue / NotificationBus 删除矩阵 — ADR-0184 投递拆分件收口

Status: proposed (级别 1–4 已执行)

## Problem

ADR-0184 PR-1 给 `EnvelopeBus` 引入两个投递拆分件:S3 入队的 `DeliveryQueue`(`lca_kernel/events/queue.py`)与 S4 派发的 `NotificationBus`(`lca_kernel/events/notification.py`)。PR-2(PersistenceWorker 接管写盘)与 `EventBus` 兼容 shim 收口之后,两者与生产真值路径的关系不对称:

1. **NotificationBus 生产零观察者**。全仓无任何 `subscribe` / `subscribe_pull` 调用方(`rg` 仅 `bus.py` 构造侧 + 测试);`EnvelopeBus.publish` 的 S4 notify 每次派发到空表,实际订阅派发走 `EventBus._fanout`。
2. **DeliveryQueue 有消费方但消费者无生产驱动**。`PersistenceWorker`(`lca_kernel/events/persistence.py`)拉该队列落盘,但其 consumer task 的唯一启动入口(`flush_for` / `flush`)生产零调用:`EventBus.publish_async` / `spine_port_append_async` / `EventSpine.append_async` / `write_port_append_async` 全链只有测试驱动。同步 `EventBus.publish` 每次仍走 S3 `submit` 入队——长驻进程内队列只进不出,`max_size=10000` 触顶后 `DeliveryQueueFull` 从同步 `publish` 上抛,属潜伏 backpressure 炸点。
3. 两个模块各自带 PR-1 时期留下的"后续 PR 接入"计划注释,与当前真实状态不符,误导后续读者重复评估。

## Proposal

四级递进删除,每级一个机械 delete-when;级别之间独立可停。**级别 1(最小 no-op 降级)随本 note 同一提交落地**,级别 2–4 为待执行提案。

### 删除矩阵

| 引用点 | 对象 | 当前状态 | 处置 | 级别 |
|---|---|---|---|---|
| `lca_kernel/events/bus.py` `EnvelopeBus.__init__` | NotificationBus 默认构造 | 已改为可选注入,未注入不构造 | 级别 2 删 kwarg | 1 ✅ |
| `lca_kernel/events/bus.py` S4 `notify` 调用 | NotificationBus | 已加 `is not None` 守卫(未注入为 no-op) | 级别 2 删守卫与调用 | 1 ✅ |
| `lca_kernel/events/__init__.py` 包根导出 | NotificationBus | 已移除导出与 import | 无需再动 | 1 ✅ |
| `lca_kernel/events/notification.py` 模块 | NotificationBus 定义 | COMPAT 标记,删除条件挂本 note | 级别 2 删文件 | 2 |
| `tests/lca_kernel/events/test_envelope_bus.py` `TestNotificationBus` | 测试 | 已改为断言默认 `None` + 显式注入派发 | 级别 2 随模块删除 | 1 ✅ |
| `lca_kernel/events/bus.py` S3 `self._queue.submit` | DeliveryQueue | 同步 publish 每次入队;生产无 consumer 拉取 | 级别 3 从同步路径移除 | 3 |
| `lca_kernel/events/bus.py` `publish_async` | DeliveryQueue + PersistenceWorker | 生产零调用方,仅测试驱动 | 级别 3 删除或改直写 | 3 |
| `lca_kernel/events/persistence.py` PersistenceWorker | DeliveryQueue 消费 | `/health` 与 `lca-ops events-delivery` 只读观测入口 | 级别 4 去队列 + 删 PersistenceWorker 别名,保留 PersistenceObserver | 4 ✅ |
| `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py` `/health` | `worker.pending_count` → `queue_depth` | 已有 graceful degradation(`except (ImportError, AttributeError)` 分支) | 级别 4 改读 PersistenceObserver;`queue_depth=0` | 4 ✅ |
| `lca/infrastructure/cli/commands/events_delivery.py` | `PersistenceWorker.default()` | 已有降级分支("PR-2 not merged yet") | 级别 4 改读 PersistenceObserver | 4 ✅ |
| `lca/plugins/events/sinks/spine_file_sink/manifest.py` COMPAT 注释 | "PR-3 cursor 完全迁 `EventBus.publish_async`" | 该迁移意图依赖级别 3 对 `publish_async` 的处置决定 | 级别 3 同 PR 更新 | 3 |
| `lca_kernel/events/queue.py` 模块 + `pyproject.toml` N818 per-file ignore | DeliveryQueue / DeliveryQueueFull 定义 | 活跃 | 级别 4 删文件 + 删 ignore 条目 | 4 ✅ |
| `tests/lca_kernel/events/test_persistence_worker.py` | 测试 | 绿 | 级别 4 重写为 `test_persistence_observer.py` | 4 ✅ |

### 级别 1 — NotificationBus no-op 降级(已落地)

`EnvelopeBus.__init__` 不再默认构造 `NotificationBus`;`notification` kwarg 保留为可选注入点,未注入时 `notification` 属性返回 `None`、S4 为 no-op。`lca_kernel/events/__init__.py` 包根移除导出。`EventBus.publish` 同步签名与返回 `EventRef` 6 字段不变。

### 级别 2 — 删 `notification.py` ✅

delete-when:`rg "NotificationBus" lca/ lca_kernel/ tests/` 仅剩 `notification.py` 自身(允许 `docs/` 归档与负向架构断言)。

动作:删 `lca_kernel/events/notification.py`;删 `bus.py` 的 kwarg / 属性 / 守卫 / TYPE_CHECKING import 与 COMPAT 块;删 `TestNotificationBus` 两个测试。

### 级别 3 — 同步 publish 去队列化 + `publish_async` 处置 ✅

前置决策:`publish_async` 全链生产零调用方,二选一——(a) 整条删除(`publish_async` + `spine_port_append_async` + `EventSpine.append_async` + `write_port_append_async`),(b) 改为不经队列直写 `PersistenceWorker` sink。选 (a)(已执行);级别 4 直接可达。

delete-when:`rg "publish_async|spine_port_append_async|append_async|write_port_append_async" lca/ lca_kernel/` = 0(选 (a);允许测试同删),且 `rg "_queue\.submit|queue\.submit" lca_kernel/events/bus.py` = 0。

### 级别 4 — 删 `queue.py` + 去 PersistenceWorker / DeliveryQueue ✅

delete-when:`rg "DeliveryQueue|DeliveryQueueFull" lca/ lca_kernel/ tests/` = 0 且 `rg "PersistenceWorker" lca/ lca_kernel/` 生产路径 = 0(允许 `docs/` 归档、COMPAT、测试负向断言);`/health` 与 `events-delivery` 改读 `PersistenceObserver`(`queue_depth=0`);`pyproject.toml` 的 `lca_kernel/events/queue.py` N818 ignore 条目同 PR 删除。

动作:删 `lca_kernel/events/queue.py`;`PersistenceObserver` 去掉 queue ctor / `_consume_loop` / `.queue`;删 `PersistenceWorker` 别名与包根导出;重写 `tests/lca_kernel/events/test_persistence_observer.py`;翻正 I-SESSION-4。

## Alternatives considered

### Why not 一次硬删两个模块?

`DeliveryQueue` 仍被 `PersistenceWorker` 消费,后者承载 `/health` 的 `queue_depth` / `fsync_policy` 观测面与 `lca-ops events-delivery` CLI;硬删会破坏 wire 观测字段与 `test_persistence_worker` 全套测试,违反契约改动闭环(消费方 + 测试未同步处置)。分四级让每步的破坏面独立可验证。

### Why not 保持现状,只写本 note 不动代码?

NotificationBus 生产零观察者,但默认构造让每个 `EnvelopeBus` 实例持一份永不派发的观察者表;且"后续 PR 接入"注释持续误导评估。no-op 降级代价约 10 行,删除条件从此机械可查;不动代码则级别 2 的 delete-when 永远差一步。

### Why not 级别 3 顺带把 `publish_async` 改写为不经队列(保留强一致异步落盘)?

`publish_async` 生产零调用方,为未使用的路径重写机制属 scope creep;其存在价值取决于 cursor 是否真迁异步落盘(`spine_file_sink` manifest COMPAT 块的意图),该决策归级别 3 前置决策,不预设。

## Acceptance criteria

- 级别 1:`rg "NotificationBus" lca_kernel/events/bus.py` 无运行时 import(仅 TYPE_CHECKING);`EventBus.publish` 同步签名与 6 字段 `EventRef` 不变;`tests/lca_kernel/events/test_envelope_bus.py` + `test_persistence_worker.py` 全绿。
- 级别 2–4:每级执行后对应 delete-when grep 归零,同 PR 删测试与配置条目,`uv run pytest` 全绿。
- 终态:`rg "DeliveryQueue|NotificationBus" lca/ lca_kernel/ tests/` = 0(允许 `docs/` 归档与负向架构断言)。

## Risks

| 风险 | 缓解 |
|---|---|
| 长驻进程 `DeliveryQueue` 无 consumer 增长至 `max_size=10000` 后 `DeliveryQueueFull` 从同步 `publish` 上抛 | 级别 3 移除同步路径入队即解除;解除前 `/health.queue_depth` 可观测该增长 |
| 级别 4 删 `PersistenceWorker` 使 `/health` 丢 `queue_depth` / `fsync_policy` 字段 | handler 已有 graceful degradation(`queue_depth` 缺省、`fsync_policy="n/a"`),`tests/transport/test_health_event_bus_field.py` 已允许该形态 |
| 级别 3 选 (a) 删除 `publish_async` 全链后,未来需要强一致异步落盘时需重新设计 | 由级别 3 前置决策显式记录;`spine_file_sink` manifest COMPAT 块的迁移意图同 PR 更新,不留悬空引用 |
| `test_bus_delivery_receipt.py` 存量失败(`UnauthorizedPublishError`,与本提案无关) | 独立缺陷跟踪,不并入本删除链 |
