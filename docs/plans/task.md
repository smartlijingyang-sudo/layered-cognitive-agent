| Task ID | Description | Status | Evidence |
|---|---|---|---|
| FE-FLOW-1 | 环境与前置服务健康检查与 agent-browser 会话初始化 | Completed | kernel:8765/health 正常，lobehub:3010 正常，daemon:2958997 正常，agent-browser open 成功进入首页 |
| FE-FLOW-2 | 前端助理创建测试（创建新助理、配置元数据、检查列表） | Completed | 对话创建架构演化助手成功（asst_a4deb4835fe3），自动物化 Home（SOUL/USER/AGENTS/skills），成功在前端与 Postgres 投影 agt_LORSp1CoEFBL |
| FE-FLOW-3 | 多轮问答与自我感知测试（首轮问答、自感知身份/能力/SOUL/USER） | Completed | 架构演化助手准确自我感知（SOUL.md 六大职责、DDD思维、权衡原则、20项技能与工具链全景） |
| FE-FLOW-4 | 修改自己与用户画像偏好演化测试（对话修改画像、回填 USER.md、修改助理配置） | Completed | 用户画像成功写入 memory/USER.md，跨轮对话准确识别“李超/系统总架构师/Python+Rust/三原则”闭环承诺 |
| FE-FLOW-5 | 创建 Skill 与技能激活调用测试（自主创建 skill、落盘校验、激活使用） | Completed | 成功调用 create_assistant_skill 安装 code-review-helper，落盘 skills/ 与 manifest.json (sha256:420a8fab...)，调用 activate_skill 激活，按五步 SOP 零容忍裸 open() 成功完成代码审查 |
| FE-FLOW-6 | 全流程问题复盘与缺陷汇总（发现的问题点、根因分析与优化建议） | Completed | 输出 5 大全流程架构与工程缺陷深度剖析报告（UI与LCA脱节、solo模型失效、BindingsView/Grants工具误杀、管家面OpenAI兼容缺口、HOME环境多账号目录割裂） |
| FIX-LCA-HOME | 固化 LCA 数据目录到权威真实用户 ~/.lca（治理多账号沙箱目录漂移） | Completed | 基础设施层引入 locator.py（get_real_user_home/get_lca_home/expand_user_path），修复 supervisor/catalog/skills/composio/lca-ops 路径，彻底删除 agy 下 .lca 软链接，单测 8/8 通过，assistant 466/466 全通，/v1/assistants 权威加载 310 个助理，home_path 严格为 /home/lichao/.lca/assistants/* |
| ADR-0246-M1 | LocalExecPort 契约收束（CapabilityGrant/EffectReceipt/FakeCompanionProvider/Adapter/架构守护） | Planned | 计划文件：docs/plans/2026-09-20-adr-0246-m1-local-exec-port.md |
