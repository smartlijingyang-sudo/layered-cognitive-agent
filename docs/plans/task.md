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
| CONV-INSTALL-1 | 预授权配对状态机增强（DevicePairingService / preauth_code 一次性免输码） | Completed | preauth_code 与 claim_preauth 落地，单测 4/4 通过，覆盖生成、免输码自动验证、单次消费与过期失效 |
| CONV-INSTALL-2 | 服务端动态脚本下发端点（install.ps1 / install.sh / pair/preauth 路由） | Completed | install.ps1、install.sh、pair/preauth、download/companion.py 路由落地，7/7 单测全通 |
| CONV-INSTALL-3 | 本机 Companion CLI 预授权直连模式（--preauth-code 自动建联常驻） | Completed | auto_pair 与 --preauth-code CLI 支持落地，支持免交互自动配对并启动常驻，单测通过 |
| CONV-INSTALL-4 | 前端 LobeHub UI 异构切换器一键安装卡片与自动绑定执行目标 | Completed | HeteroDeviceSwitcher 补丁升级落地，支持免输码一键命令（PowerShell/Bash）与上线自动绑定执行目标，23/23 补丁验证全通 |
| CONV-INSTALL-5 | 端到端全链路对话式安装与自动配对集成测试 | Completed | test_conversational_auto_install_and_pairing_flow 全链路端到端测试 100% 通过（POST /api/device/pair/preauth 生成一键脚本，动态获取 install.ps1/install.sh，Companion 零输入自动配对获取 machineToken，WS 握手在线，LocalExecPort 执行命令与文件写入全链路打通），ADR-0246 & CONV-INSTALL 52/52 测试全数通过 |
| DEBUG-405-HMR | 调查并修复前端 /runs 405 Method Not Allowed 与 Vite HMR 连接失败根因 | Completed | 根因一（405）：前端 file_proxy_rewrite 补丁脱落导致 next.config.ts 与 vite.config.ts 缺失 /lca-api 代理规则，请求命中 Next 404 并 307 重定向至 / 引发 405，通过 patch_lobehub.py 补全补丁并重启生效，POST /lca-api/runs 恢复 202 Accepted；根因二（HMR）：旧浏览器标签页使用过期的 wsToken（DhS_...）尝试连接已重启的 Vite 服务被拒，新标签页或刷新后携带有效 token（X1spt...）已建立 101 Switching Protocols 正常握手；LobeHub（3010/9876）与全栈服务现已健康运行 |
| DEBUG-RUN-ANALYSIS | 深入调试最后一次 run：分析 search_skill 触发根因、五状态向导泄露给用户原因及终止未继续的原因 | Completed | 根因追溯闭环：1. search_skill 出现根因：内核运行于 web-standard profile，缺 assistant-runtime bundle 导致无 create_assistant 内置工具，prompt 注入 20 项通用工具与 available_skills，诱导模型退化调用 search_skill/activate_skill；2. 向导泄露原因：activate_skill 注入 create-assistant/SKILL.md，模型执行前置检查发现缺失 create_assistant，按指南“告知用户”时将内部五状态 SOP 当解释性文本全盘输出；3. 终止未继续根因：纯文本回复触发 LCA 认知循环 terminal.commit 正常收敛，且前期 askUserQuestion 答案因前端触发新 Run 覆盖 topic 最新指针，导致 resume 请求命中运行中新 Run 引发 409 Conflict 答案丢弃 |
| REFACTOR-CLEANUP-BRAINSTORM | 第一性原理架构重构头脑风暴：明确范围、提炼方案、消除垃圾逻辑与建立业界范式 | Completed | 架构设计文档与落地实施计划均已就绪并获得用户确认 |
| REFACTOR-TASK-1-PROFILE | 软化 Composio 阻断依赖 & 平台默认 Profile 合流为 web-assistant | Completed | Composio required:false，supervisor/cli/config/profile 默认 profile 收敛至 profiles/web-assistant.yaml，13 plans validated ok，单测 test_supervisor_profile_default.py 3/3 passed |
| REFACTOR-TASK-2-RESUME-BINDING | 网关 _dispatch_resume 支持精准 run_id 寻址与前端补丁对齐 | Completed | CreateRunRequest 增加 run_id 字段，decode_create_run 解析 run_id，_dispatch_resume 优先使用显式 run_id 寻址消除 409 竞态，execute.ts 与 executeGatewayRun.ts 携带 run_id，patch_lobehub.py 23/23 生效，test_resume_run_id_binding.py 3/3 passed |
| REFACTOR-TASK-3-SKILL-HYGIENE | 彻底重构 create-assistant/SKILL.md 提示词与消除内部架构泄露 | Completed | create-assistant/SKILL.md 提示词重构，删除 web-assistant/profile/系统管理员等泄露词汇，建立无工具自然友好提示防线与五步向导 SOP；search_skill 描述剔除诱导短语；单测 test_create_assistant_skill_hygiene.py 2/2 passed |
| REFACTOR-TASK-4-INTEGRATION-VERIFY | 端到端服务重启与全链路集成验证 | Completed | 1. 服务重启：kernel-restart 重启至 web-assistant profile（pid=1805823，13 plans ok，2736 fibers ok，health 探针 ok，加载 310 个助理）；2. 单测回归：13/13 全数通过；3. 真实多轮活体验证（run_3e591218c03f）：0 次误调 search_skill，0 处架构/状态机泄露，4 轮问答（部门→角色→名字→职责）经精准 run_id 寻址顺畅恢复（0 次 409 冲突），成功调用 create_assistant 物化落盘 asst_44dd568b3bf9（架构小助，22 项技能，SOUL 8KB），Postgres 权威投影 agt_erElPnOEkHdF 闭环 |
| ASST-CAPABILITY-VERIFY | 架构小助专属自治域能力实测：自我感知、创建Skill、记忆持久化与跨轮召回 | Completed | 1. 自我感知与MD/技能感知（run_f69b7e39c90d）：准确自述身份职责、SOUL.md六大职责与三原则、识破USER.md空白、准确枚举20项已挂载技能与工具链；2. 创建Skill（run_835bc0e18f63）：成功调用专属工具create_assistant_skill，物化落盘arch-doc-standards（manifest.json content_hash=78fc2f...，SKILL.md 146行高质量ADR规范）；3. 记忆持久化与召回（run_8742e94dd32b & run_570f261afec4）：主动调memory_add及reflect.memory.extract自动沉淀7条事实至semantic.json，优化MemorySearchTool多词分词评分（3/3单测全通），次轮对话零幻觉100%精确召回李超/系统总架构师/Rust+Python/架构三原则全景信息 |
| INSTALL-TYPESAFE-SKILL | 安装并验证 TypeSafe Skill 与 Python SDK 环境 | Completed | 通过 `npx -y skills add typesafe-ai/skills --skill typesafe-ai` 成功安装到 `.agents/skills/typesafe-ai` 并同步至 `.agent/skills/typesafe-ai`；生成 `skills-lock.json`；安全写入 `TYPESAFE_API_KEY` 至 `.env`；安装 `typesafe-sdk`；通过 live System One Noul 测试调用（返回 0.95），验证通过 |
| PUSH-TASK-1 | 【技能闭环】激活新创建的 arch-doc-standards 技能并实际编写落盘 ADR | Completed | 成功调用 activate_skill 激活 arch-doc-standards，严格遵循 SKILL.md 中的 ADR 规范与模板，在私有自治域 workspace/docs/adr/ 成功落盘《ADR-0301: 架构小助专属记忆与技能自演化机制》（142行/9.5KB，含双层架构图、四方案权衡表、已知风险缓解与三原则对齐） |
| PUSH-TASK-2 | 【记忆演化】记忆冲突更新（Rust+Go废除Python）与敏感删除风控（删除三原则） | In Progress | 待发起偏好变更、敏感删除确认与次轮零污染召回测试 |

| PUSH-TASK-3 | 【自我修正】长期记忆反思回填 USER.md 与自主演化 SOUL.md 核心使命 | Pending | 待测试画像回填与 update_assistant_soul 契约更新落盘 |
| PUSH-TASK-4 | 【跨机协作】结合本地 Companion 执行机器探查（LocalExecPort 边界实测） | Pending | 待测试通过本地 companion 读取 git log 与系统状态回执闭环 |
| BRAINSTORM-JEV-CONTEXT | 探索项目上下文与 TypeSafe/Jev 能力契合点 | Completed | 已梳理 LCA 认知五相（Think/Gate/Reflect/Route）痛点与 Jev 原语（Noul/Choice/Score）对应切入点 |
| BRAINSTORM-JEV-QUESTIONS | 澄清业务偏好与核心痛点约束（单步提问） | In Progress | 正在与用户沟通首要痛点与接入目标场景 |
| BRAINSTORM-JEV-APPROACHES | 提出 2-3 种具体整合架构方案与权衡 | Pending | 待用户回答澄清问题后输出方案对比与推荐 |
| BRAINSTORM-JEV-DESIGN-SECTIONS | 逐步呈现设计细节并获取用户审批 | Pending | 待方案选型确认后推进 |
| BRAINSTORM-JEV-DESIGN-DOC | 沉淀设计文档至 docs/plans/ 并提交 | Pending | 待设计审批通过后落地 |
| BRAINSTORM-JEV-TRANSITION | 转换至实施计划制定（writing-plans） | Pending | 终态推进 |


