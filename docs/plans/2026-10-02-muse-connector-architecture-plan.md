# 工业级 7 层连接器架构实施计划 (Muse Connector Architecture Plan)

> **前置设计**: [docs/plans/2026-10-02-muse-connector-architecture-design.md](file:///home/lichao/layered-cognitive-agent/docs/plans/2026-10-02-muse-connector-architecture-design.md)  
> **执行模式**: Antigravity 单流严格顺序执行 (Single-Flow Execution)  
> **核心原则**: TDD 先测后写、AP-01 负向边界声明、AP-02 自动化不变量保证

---

## 负向边界保护清单 (Does NOT Own)
- **绝对不修改**: `lca/cognition/` 认知主循环五阶段核心状态机（perceive-think-act-reflect-remember）；
- **绝对不修改**: LobeHub 官方上游代码仓库源码（所有前端协同严格限定于 `deploy/lobehub/patches/` 声明式补丁）；
- **绝对不修改**: 宿主机全局网络与系统运维配置，所有外部资产严格归属于 `~/everything-library`。

---

## 任务拆解与执行清单

### 阶段一：连接器运行时底座与状态机 (M1)

#### 任务 1.1: 连接状态机与核心契约 (TDD)
- **目标**: 建立 `lca/infrastructure/connectors/core/state.py`，定义 `ConnectionState` 枚举与流转规则；定义 `ConnectorSpec` 与 `ConnectionMetadata` 不变模型。
- **不变量覆盖**: INV-02（状态机确定性）、INV-01（模型字段严禁包含未脱敏 Secret）。
- **验证命令**: `pytest tests/connectors/test_connector_state_machine.py`

#### 任务 1.2: 安全凭证提供者与 Composio 桥接器
- **目标**: 建立 `lca/infrastructure/connectors/core/vault.py`，负责从 `~/.lca/users/<user_id>/connectors/` 安全索引凭证元数据，与 Composio API 隔离交互，保证 Token 绝不泄露至模型上下文。
- **不变量覆盖**: INV-01（Token 零暴露）。
- **验证命令**: `pytest tests/connectors/test_connector_vault.py`

---

### 阶段二：首个切片 Gmail CLI 封装与 Manifest / SKILL.md (M2)

#### 任务 2.1: Gmail CLI 模拟驱动与命令分发
- **目标**: 建立 `lca/infrastructure/connectors/gmail/cli.py`，实现 `+send`、`+read`、`accounts`、`status`、`connect`、`disconnect` 等命令分发。
- **不变量覆盖**: INV-02（未连接时 status 必抛结构化 JSON）、INV-06（`+send` 强制依赖 `--upload` 暂存文件）。
- **验证命令**: `pytest tests/connectors/test_gmail_cli.py`

#### 任务 2.2: Manifest 规范与 SKILL.md 动态物化
- **目标**: 落地 `lca/infrastructure/connectors/gmail/manifest.yaml`，并编写生成器将 `SKILL.md`（内嵌成本指南、命令速查与卡片唤起规则）挂载到助理技能库。
- **不变量覆盖**: INV-03（SKILL 规范指引卡片协议）。
- **验证命令**: `pytest tests/connectors/test_gmail_skill_generation.py`

---

### 阶段三：LobeHub 卡片协议联动与 Prompt 认知注入 (M3)

#### 任务 3.1: 会话启动 Prompt 注入已连接服务 (ConnectedServicesSection)
- **目标**: 在 `lca/cognition/context/` 或 `runtime_env.py` 注册 `ConnectedServicesSection`，在 System Prompt 注入仅占 ~50 tokens 的连接概览（解决“不知道自己连接了 GitHub/Gmail”的断层）。
- **不变量覆盖**: 消除 2000 字符溢出截断盲区，保证 Agent 拥有先验连接信念。
- **验证命令**: `pytest tests/cognition/test_connected_services_prompt.py`

#### 任务 3.2: 唤起卡片协议与 LobeHub `ConnectorAuthCard` 闭环
- **目标**: 校验 Agent 遇到 `not_connected` 时输出标准 `[widget:connector_auth?appName=Gmail&authUrl=...&connectionId=...]`，并验证 LobeHub 前端补丁正确擦除文本并挂载卡片。
- **不变量覆盖**: INV-03（卡片协议绝对优先于裸链接）。
- **验证命令**: `pytest tests/deploy/test_connector_auth_card_patch.py`

---

### 阶段四：双层正交权限引擎与滑动窗口硬配额 (M4)

#### 任务 4.1: 本地 Action 权限规则加载与拦截器
- **目标**: 建立 `lca/infrastructure/connectors/core/permissions.py`，加载 `permissions.json`，在 Action 执行前对 `DENY`、`ASK`、`ALLOW` 进行强校验。
- **不变量覆盖**: INV-04（双层权限硬拦截）。
- **验证命令**: `pytest tests/connectors/test_connector_permissions.py`

#### 任务 4.2: 滑动窗口硬配额执行器 (Rate Limiter)
- **目标**: 建立 `lca/infrastructure/connectors/core/rate_limiter.py`，实现 60 秒滑动窗口单位计算；超限直接阻断并返回结构化 `connector_rate_limited` 与 `retry_after_seconds`。
- **不变量覆盖**: INV-05（硬限流窗口 100% 拦截）。
- **验证命令**: `pytest tests/connectors/test_connector_rate_limiter.py`

---

### 阶段五：全链路集成回归与活体验证 (M5)

#### 任务 5.1: 全量测试不变量断言套件 (INV-01 ~ INV-08)
- **目标**: 落地 `tests/scenario/test_muse_connector_invariants.py`，一次性断言 INV-01 至 INV-08 全部通过。
- **验证命令**: `pytest tests/scenario/test_muse_connector_invariants.py`

#### 任务 5.2: 全面门禁与端到端实测验证
- **目标**: 运行 `ruff check`、`ruff format --check`、`git diff --check`，重启内核进行真实对话验证。
