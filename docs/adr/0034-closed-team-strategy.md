# ADR-0034: 封闭 TeamStrategy 与 TeamSpec 单一事实来源

## 状态
Accepted

## 背景
ADR-0030 钉死了公共面名字，ADR-0033 让声明式输入贯穿组合管线，但团队侧
仍保留了一套运行期间接层，导致 `compose_team` 与 `TeamOrchestrator.run`
概念混杂、难以维护与扩展：

1. **一个事实五份编码**：团队形态同时存在于入参形态（lead XOR coordination）、
   `strategy_key` 字符串、`TeamConfig` 字段、`TeamContext` 结构信号
   （lead/member_status 有无）、strategy 实例类型五处，靠 XOR 校验与
   运行期重复校验手工对账。
2. **`TeamContext` 杂物袋**：9 个 Optional 字段混装身份/参与者/行为参数/
   基础设施，每个消费方只用一个子集却必须防御全部字段；同一批成员以
   members / teammates / transport handler / role_order 四种形态重复存在。
3. **Lead 特殊旁路**：composer 对 lead 做专门分支（board 布线、session 模板），
   与 coordination 路径走两套装配逻辑——而本质上 lead 只是「把决定下一步的
   权力交给某个成员」，是一种治理方式，不是特殊机制。
4. **遥测内联**：`TeamOrchestrator.run` 40 行中真正的行为只有 1 行，其余是
   attrs 装配与 getattr 反射；编排器还逐字段抄写 context。
5. **运行期回退链**：swarm/debate 构造期已收到 max_rounds，运行期仍回退
   读 `context.config`；`strategy=` 覆盖参数架空策略注册表。

共同根因：**团队形态没有一个唯一事实来源，运行期仍在重新拼凑形态信号**。

## 决定

本质模型一句话：**团队 = 一份声明（谁 + 由谁决定下一步），在组合期被编译成
一个封闭的、可直接 run 的策略；运行期没有编排器、没有上下文包、没有键值间接。**

1. **TeamSpec / Governance（contracts/agent_spec.py）**：
   `Governance = LeadSpec | Coordination`，团队形态由单一槽位表达，XOR 在
   类型层面不可表示非法组合；`TeamSpec`（members + governance + 共享记忆层 +
   委派重试上限 + 观测覆盖）是团队组合根的唯一声明式输入。
   `strategy_key_for_governance` 是唯一派生入口：strategy_key 仅作注册表
   分发键与遥测标签，组合期派生一次，运行期不流转。
2. **封闭 TeamStrategy**：协议签名 `run(objective: str) -> Result`，无上下文
   参数。每种 Governance 经注册表工厂闭合为一个实现，构造期注入全部依赖：
   协调型策略持 `TeamStage`（成员 + MemberInvoker）与轮次/图参数；
   `LeadStrategy` 持封闭 lead agent + mandate + 名册 + board 模板，
   每次 run 新建控制会话（行为不变）。**Lead 与 coordination 走同一条
   「注册表 → 策略工厂 → 封闭策略」路径，composer 无 lead 特判。**
3. **布线类型不进领域词汇**：`MemberInvoker`（策略调用成员的唯一通道，
   默认实现 `TransportMemberInvoker`）、`TeamStage`、`TeamAssembly`
   （工厂 resolve 期只读装配视图）只存在于组合期。
4. **TeamHandle 取代 TeamOrchestrator**：运行句柄只做三件事——bind 观测、
   发 run.team / run.plan 场景卡、委派策略；遥测 attrs 由 L0
   `TeamTraceProfile` + 装配函数提供（组合期从角色画像派生，无反射）。
5. **删除**：`TeamContext`、`TeamConfig`、`team_lead_mandate`、
   `strategy_key_for_lead`、swarm/debate 运行期 max_rounds 回退链、
   `compose_team` 的 `strategy=` 覆盖参数（自定义策略走
   `register_orchestration_strategy`）。
6. **组合期 fail-fast**：成员角色非空且不重复在组合期校验
   （原先空角色在运行期才报错）。

## 后果
- 正面：团队形态单一事实来源；运行期零解包零校验；新增协作方式 = 一个
  Coordination 类型 + 一个策略类 + 注册表一行；遥测与行为分离；
  策略单测无需再搭 transport/context 脚手架。
- 负面：breaking change——`TeamStrategy.run` 去掉 context 参数，
  编排注册表工厂签名改为 `(TeamAssembly) -> TeamStrategy`，
  `TeamContext` / `TeamConfig` 删除；无 shim（沿用 ADR-0030 的 breaking 策略）。
- 行为不变：公共面（Agent / Team / TeamLead / LeadMandate / Coordination）、
  XOR 错误文案、7 个策略注册键、span 树与属性键值、Result 语义全部保持。

## 相关
- Supersedes: ADR-0030 第 5 条（策略注册键保留，工厂签名与运行期模型被本 ADR 取代）、ADR-0033 第 3 条（编排工厂签名）
- Keeps: ADR-0030 公共面与一元领域语言、ADR-0029 封闭对象图、ADR-0033 spec 化门面、ADR-0015 contracts 纯净、ADR-0005 组合根三职责
