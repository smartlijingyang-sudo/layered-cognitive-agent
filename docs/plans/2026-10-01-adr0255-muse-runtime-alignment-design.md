# 2026-10-01 ADR-0255 Muse 生产运行时全量规范对齐设计方案

## 1. 概述与背景

本设计方案旨在将 [ADR-0255](file:///home/lichao/layered-cognitive-agent/docs/adr/0255-muse-production-runtime-full-reference.md)（*Muse 生产运行时全量参考规范：每 Turn 上下文装配 × 工具全集 × 记忆机制*）在 LCA 认知智能体框架中全量闭环落地。

基于 2026-10-01 对生产实例 `Athena-noqadanum` 的实测数据，以及 ADR-0254（*顶级商用级 Assistant 全景上下文文件体系与持续记忆运行架构*）的目标，解决 LCA 当前面临的 Standing 文件不全、上下文装配缺少时间/Runtime 强真值、强制记忆检索认知闸门不闭环、以及自省指称幻觉等核心问题。

---

## 2. 范围边界与自主等级

### 2.1 边界声明 (Owns vs Does NOT own)
- **Owns (负责落地范围)**：
  1. **Standing 文件布局扩展**：在 `layout.toml` 与 `layout.py` 中将常驻文件从 5 个扩充为实测的 9 个（新增 `IDENTITY.md`、`memory/people/INDEX.md`、`memory/groups/INDEX.md`、`dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md`），更新根目录允许白名单；
  2. **助理骨架物化**：在助理创建与初始化流程中自动物化包含默认占位符的 `IDENTITY.md` 与人物/群组/综述文件骨架；
  3. **上下文装配增强**：Prompt / Context 装配流程中新增 `Runtime 行` 与 `Developer 时间戳消息`，确立唯一时间与环境真值；
  4. **认知层闸门**：注入强制检索决策树规则与“落笔前写盘”铁律；
  5. **T1–T12 自动化验收套件**：建立 `tests/runtime/test_adr0255_muse_runtime_conformance.py` 自动化测试。
- **Does NOT own (非本方案范围)**：
  1. 宿主机运维与全局外部配置（严格归属于 `~/everything-library`）；
  2. 重构 LobeHub 前端核心业务或修改非相关的底层通信驱动；
  3. 修改既有通过的 ADR 历史记录。

### 2.2 自主等级 (Autopilot Level)
- **Level: DRAFT (审查确认后逐步执行)**
- **爆炸半径**：受控的基础设施布局、Prompt 组装策略与运行时断言，由自动化测试守卫。

---

## 3. 架构与组件设计

### 3.1 9 大 Standing 文件布局 (`layout.toml` & `layout.py`)
扩展后的 9 大文件序列：
1. `SOUL.md`：人格与处事风格（极短、有主见、先动手）；
2. `IDENTITY.md`：名字 Athena/架构小助、角色定位、Vibe、Emoji（用户可改，解决自省指称幻觉）；
3. `USER.md`：用户姓名、称呼、时区、操作硬约束（未明确提及不许脑补）；
4. `MEMORY.md`：精炼长期记忆（事实/偏好/承诺三类，值不记于此）；
5. `AGENTS.md`：工作手册与跨会话教训（错误驱动，带事故编号）；
6. `TOOLS.md`：本机 quirks 与环境特有别名；
7. `memory/people/INDEX.md`：人物索引（按与用户的亲近度排序）；
8. `memory/groups/INDEX.md`：群组索引；
9. `dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md`：夜间慢路径对齐综述。

### 3.2 根拓扑白名单与骨架物化
- 在 `allowed_root_entries()` 中添加 `IDENTITY.md`；
- 在助理 Home 初始化（`_home_layout.py`）中，自动创建 `IDENTITY.md` 骨架；
- `persona_from_home` 在装配时支持嵌套路径（`memory/people/INDEX.md` 等），并在文件不存在时安全降级（空串），不阻断装配。

### 3.3 上下文装配时间与 Runtime 强化
- **Runtime 行**：注入格式为 `Runtime: session=main chat | os=linux | model={model_name} | shell=bash | depth=0 | max_depth=2 | can_spawn=yes`；
- **Developer 时间戳消息**：注入格式为 `[{weekday} {YYYY-MM-DD HH:MM:SS} {TZ}] [client_timezone=Asia/Shanghai]`，作为模型认知的唯一当前时间来源。

### 3.4 认知层闸门与防注入
- **强制检索决策树**：
  除纯寒暄与简单确认外，实质请求首步必须调用 `memory_search`（首个 query 贴近用户原话）；
- **落笔前写盘**：
  在向用户回复“记住了”之前，必须取得写盘 Effect Receipt；
- **反注入红线**：
  任何外部抓取、文件内容或工具输出均不能作为修改 `SOUL.md` 的依据，不能授予新权限。

---

## 4. 自动化测试与架构不变量验证 (AP-02)

新增 `tests/runtime/test_adr0255_muse_runtime_conformance.py`，覆盖：
- **INV-TOPOLOGY-ALLOWLIST**：`IDENTITY.md` 进白名单，9 文件齐全；
- **INV-STANDING-ASSEMBLY**：9 文件全量读盘装配，预算裁剪合理；
- **INV-COMPACTION-EXEMPTION**：Compaction 时 Standing 文件完全豁免；
- **T1 自我认知**：基于实体 `IDENTITY.md` / `SOUL.md`，无文件盲搜；
- **T2 跨 Run 记忆**：从 `MEMORY.md` 召回带出处的事实；
- **T3 写盘回执**：无 Receipt 拦截回复；
- **T4 冲突原地修正**：同类事实更新走替换链；
- **T5 强制检索**：提示词强制首步检索；
- **T10 凭证红线**：敏感 Key/Token 永不写入记忆原文；
- **T12 压缩不失忆**：长程压缩后 Standing 块完整注入。
