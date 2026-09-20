| Task ID | Description | Status | Evidence |
|---|---|---|---|
| FE-FLOW-1 | 环境与前置服务健康检查与 agent-browser 会话初始化 | Completed | kernel:8765/health 正常，lobehub:3010 正常，daemon:2958997 正常，agent-browser open 成功进入首页 |
| FE-FLOW-2 | 前端助理创建测试（创建新助理、配置元数据、检查列表） | Completed | 对话创建架构演化助手成功（asst_a4deb4835fe3），自动物化 Home（SOUL/USER/AGENTS/skills），成功在前端与 Postgres 投影 agt_LORSp1CoEFBL |
| FE-FLOW-3 | 多轮问答与自我感知测试（首轮问答、自感知身份/能力/SOUL/USER） | Completed | 架构演化助手准确自我感知（SOUL.md 六大职责、DDD思维、权衡原则、20项技能与工具链全景） |
| FE-FLOW-4 | 修改自己与用户画像偏好演化测试（对话修改画像、回填 USER.md、修改助理配置） | Completed | 用户画像成功写入 memory/USER.md，跨轮对话准确识别“李超/系统总架构师/Python+Rust/三原则”闭环承诺 |
| FE-FLOW-5 | 创建 Skill 与技能激活调用测试（自主创建 skill、落盘校验、激活使用） | Completed | 成功调用 create_assistant_skill 安装 code-review-helper，落盘 skills/ 与 manifest.json (sha256:420a8fab...)，调用 activate_skill 激活，按五步 SOP 零容忍裸 open() 成功完成代码审查 |
| FE-FLOW-6 | 全流程问题复盘与缺陷汇总（发现的问题点、根因分析与优化建议） | Completed | 输出 5 大全流程架构与工程缺陷深度剖析报告（UI与LCA脱节、solo模型失效、BindingsView/Grants工具误杀、管家面OpenAI兼容缺口、HOME环境多账号目录割裂） |
| FIX-LCA-HOME | 固化 LCA 数据目录到权威真实用户 ~/.lca（治理多账号沙箱目录漂移） | Completed | 基础设施层引入 locator.py（get_real_user_home/get_lca_home/expand_user_path），修复 supervisor/catalog/skills/composio/lca-ops 路径，彻底删除 agy 下 .lca 软链接，单测 8/8 通过，assistant 466/466 全通，/v1/assistants 权威加载 310 个助理，home_path 严格为 /home/lichao/.lca/assistants/* |
| ADR-0246-M1 | LocalExecPort 契约收束（CapabilityGrant/EffectReceipt/FakeCompanionProvider/Adapter/架构守护） | Completed | 契约已冻结，MachineLocalExecAdapter/FakeCompanionProvider 闭环，11/11 测试通过，ADR-0246 M1 标记 Implemented |
| ADR-0246-M2 | 控制面配对服务与路由（DevicePairingService / /api/device/pair/* 10 HTTP + 1 WS） | Completed | DevicePairingService 状态机落地，machineToken 校验闭环，10/10 路由单测通过 |
| ADR-0246-M3 | Local Companion Client（CompanionClient / scripts/lca-companion CLI） | Completed | CompanionClient/CLI 落地，支持配对、重连、本地能力白名单拦截，6/6 单测通过 |
| ADR-0246-M4 | 前端 UI 异构切换器配对卡片（HeteroDeviceSwitcher 补丁与数据刷新） | Completed | execution_target 补丁升级，支持输入配对码调用 verify 并 mutate 刷新设备列表，patch 校验 23/23 ok |
| ADR-0246-E2E | 全链路真实端到端集成验证（Live Gateway + Companion Client + LocalExecPort + 安全边界） | Completed | test_user_machine_full_flow 全链路通过（WS配对连接、指令执行、文件读写、超期 Grant 拒绝、越权拒绝、离线兜底），ADR-0246 43/43 测试全数通过 |
| CONV-INSTALL-1 | 预授权配对状态机增强（DevicePairingService / preauth_code 一次性免输码） | Planned | 计划文件：docs/plans/2026-09-20-conversational-local-machine-connection-plan.md Task 1 |
| CONV-INSTALL-2 | 服务端动态脚本下发端点（install.ps1 / install.sh / pair/preauth 路由） | Planned | 计划文件：docs/plans/2026-09-20-conversational-local-machine-connection-plan.md Task 2 |
| CONV-INSTALL-3 | 本机 Companion CLI 预授权直连模式（--preauth-code 自动建联常驻） | Planned | 计划文件：docs/plans/2026-09-20-conversational-local-machine-connection-plan.md Task 3 |
| CONV-INSTALL-4 | 前端 LobeHub UI 异构切换器一键安装卡片与自动绑定执行目标 | Planned | 计划文件：docs/plans/2026-09-20-conversational-local-machine-connection-plan.md Task 4 |
| CONV-INSTALL-5 | 端到端全链路对话式安装与自动配对集成测试 | Planned | 计划文件：docs/plans/2026-09-20-conversational-local-machine-connection-plan.md Task 5 |

