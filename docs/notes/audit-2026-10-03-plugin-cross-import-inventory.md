# 审计记录：插件间直接 import 存量清单与解耦排期（2026-10-03）

- 基线 commit：`588e51c29`（main）
- 来源：夜战深审 P2 #7（`hidden_files/audit-2026-10-02-daytime.md` §6）——"arch 轮立项：按对排期 seam 化（先 transport→domain、domain→assistant）"
- 性质：**只读盘点 + 排期提案，不动手改代码**。本文件是现状清单，不是违规判决；是否违规需按插件注册契约逐个案判定。

## 1. 方法（诚实声明）

- 扫描范围：`lca/plugins/**` 下全部 `.py`
- 计数口径：顶层目录粒度——`lca/plugins/<owner>/...` 中的 `from lca.plugins.<target>...` / `import lca.plugins.<target>...`（`<target> != <owner>`）
- **只统计绝对 import，不含相对 import**；`private-target` 列=目标路径含 `_` 前缀段（如 `._session_observe`）
- 与 2026-10-02 深审的"19 对 / 54 处"口径不同（彼时方法未记录），**数字不可直接对比趋势**；本次以本口径为准重新基线化

## 2. 清单（28 对 / 82 处）

owner → target ｜ 处数 ｜ 其中私有模块穿透

| owner | target | 处数 | 私有穿透 |
|---|---|---|---|
| transport | events | 10 | 10 |
| domain | assistant | 8 | 7 |
| transport | domain | 7 | 0 |
| collaboration | transport | 5 | 0 |
| observation | events | 5 | 5 |
| control_contributions | loop | 5 | 0 |
| transport | loop | 4 | 0 |
| avatar | transport | 4 | 0 |
| transport | session | 3 | 0 |
| transport | assistant | 3 | 2 |
| transport | observability | 3 | 0 |
| collaboration | state | 3 | 0 |
| composition | composer | 3 | 0 |
| events | session | 2 | 0 |
| assistant | transport | 2 | 0 |
| composer | act | 2 | 0 |
| composer | journal | 2 | 0 |
| collaboration | tools | 1 | 0 |
| collaboration | composer | 1 | 0 |
| primitive | events | 1 | 0 |
| session | observability | 1 | 0 |
| observation | session | 1 | 0 |
| composer | events | 1 | 0 |
| composer | loop | 1 | 0 |
| tools | composer | 1 | 0 |
| observability | journal | 1 | 0 |
| observability | session | 1 | 0 |
| prompts | composer | 1 | 0 |

实证样本（抽查）：

- `transport → events` 10 处全部落在 `lca/plugins/transport/webserver/carrier/runs/lifecycle/lifecycle.py`（:106/:213/:253），目标是 events 插件的**私有**会话 helper（`events._session_observe.set_session`、`events.publishers._session_publish.set_publish_session/reset_publish_session`）
- `domain → assistant` 8 处落在 `lca/plugins/domain/assistant/catalog/*`（manifest/plan_overlay/soul/events/plugin/handlers），目标是 assistant 插件的**私有**布局/事件模块（`assistant.home._home_layout`、`assistant.events._events`）
- `transport → domain` 7 处落在 `lca/plugins/transport/webserver/routes_1/routes_assistants/*`（codecs/jobs/status_screen/standing_files/lobehub/profile），目标是 domain 插件 catalog 的公开异常（`AssistantCatalogError`）

## 3. 分类与排期提案

**P0 私有穿透（24 处，优先解耦）**：transport→events（10）、domain→assistant（7）、observation→events（5）、transport→assistant（2）。
修法方向：目标插件把被穿透的私有能力升为公开 seam（如 events 会话上下文的公开 API / carrier 注入），或反转依赖方向。私有模块跨插件 import 绕过一切公开契约，是最脆弱的耦合。

**P1 公开跨插件（按量排队）**：transport→domain（7）、collaboration→transport（5）、transport→loop（4）、avatar→transport（4）、transport→session（3）、transport→observability（3）、collaboration→state（3）、余下小项。
修法方向：个案判定——能走事件总线/声明式 seam 的走 seam；确属同构内聚的标记 accepted-by-design。

**建议 accepted-by-design（不动，待确认）**：control_contributions→loop（5，`control_contributions/__init__.py` 重导出 loop control slot 的 executor 实现，属控制贡献契约的注册聚合）；composition→composer（3）、composer→{act,journal,events,loop}（6）、prompts→composer、tools→composer、collaboration→composer（框架装配线）。**需 Athena/李超确认后方可定为 accepted**，本轮不擅自定案。

## 4. 交接

- 动手归属：quality lane 按"对"认领（一次只解一对，测试背书），iter-tests 补回归断言；arch 轮只跟踪清单数字变化
- 与审计建议的差异说明：审计建议"先 transport→domain、domain→assistant"；本轮实证显示 transport→events 私有穿透量更大且更脆弱，故把 transport→events 提至 P0 首位——**这是提案排序调整，非架构决策**，最终顺序由 Athena/李超拍板
