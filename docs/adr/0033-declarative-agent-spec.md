# ADR-0033: 声明式 AgentSpec 与协议化门面

## 状态
Accepted

## 背景
ADR-0030 钉死了公共面名字（Agent / Team / TeamLead），但未钉死形状；
ADR-0029 要求封闭对象图（构造后不可修改）。两者叠加产生四处结构性债务：

1. **门面游离于协议体系**：L3 具体类都显式实现 `AgentUnit` / `TeamUnit`，
   L4 门面三个类却是裸 class——`Agent` 不满足 `AgentUnit`（无
   `role_profile` / `resume` / `cancel`），`TeamLead` 退化为
   `tuple[CognitiveAgent, LeadMandate]` 在层间传递。
2. **构造输入即抛**：`Agent.__init__` 立即组装后丢弃全部声明式输入，
   只留成品。Team 需要给成员注入共享记忆 / 观测 / 决策门时，唯一合法
   路径是"从头重建"，只能靠 `_tools_from_agent` / `_llm_from_agent` /
   `_obs_from_agent` 从封闭成品图的私有属性反向挖零件，且重组有损
   （自定义 brain / memory 选择被静默丢弃）。
3. **进程级全局单例残留**：`_get_default_composer` 是 ADR-0024 清理
   全局单例时的漏网之鱼；`composer=` 逃生参数零调用方。
4. **组合根 if/elif 特判**：编排注册表工厂是无参 `() -> TeamStrategy`，
   装不下参数化策略（Swarm / Debate / Graph），`compose_team` 只能按
   策略键 if/elif 特判，违背注册表分发约定。

共同根因：**声明式输入没有被当作一等实体贯穿构造管线，管线里传递的
是已封闭的成品**。

## 决定
1. **AgentSpec / LeadSpec 值对象**（`contracts/agent_spec.py`）：
   `AgentSpec = RoleProfile + LLM/工具 + 预算 + 组件选择`，frozen
   dataclass，是组合根的唯一声明式输入；`LeadSpec = AgentSpec +
   LeadMandate`，全层统一表示 lead，废除 tuple 参数。
2. **门面持 spec + 协议化**：`Agent` 显式实现 `AgentUnit`（持有 spec
   与组装成品），`Team` 显式实现 `TeamUnit`，`TeamLead` 是 `LeadSpec`
   的门面持有者。Team 组合期从 spec 重建成员图——无损、可重复、
   零内省。
3. **编排工厂签名 `(Coordination | None) -> TeamStrategy`**：
   参数化策略在 resolve 期从 Coordination 提取 max_rounds /
   execution_graph，`compose_team` 的 if/elif 链收回注册表；
   contracts 同步把 `strategy_key_for_coordination` /
   `gate_name_for_mandate` 改为声明式类型映射表。
4. **无进程级 composer 单例**：门面在未显式注入 composer 时各自构造
   独立默认 composer；`_get_default_composer` 删除，
   `Team.__init__` 内联注册表解析删除，字符串解析收敛到 composer
   单一路径。自定义注册须显式贯通 `Agent(composer=...)` 与
   `Team(composer=...)`。
5. **注册键命名常量**：`*_CHOICE_*`（memory / observability /
   state_store / brain）定义在 `contracts/agent_spec.py`，与
   `defaults.py` 注册键同源，消灭裸字符串。

## 后果
- 正面：组合根不再依赖私有属性内省；重组无损；门面落入协议体系可被
  `isinstance` 与 mypy 双重校验；参数化策略与普通策略同一条注册表路径。
- 负面：breaking change——`AgentComposer.compose` 改收 `AgentSpec`，
  `compose_team` 成员参数改为 spec 列表，lead 参数改为 `LeadSpec`；
  无 shim（沿用 ADR-0030 的 breaking 策略）。

## 相关
- Extends: ADR-0030（公共面名字不变，补齐形状契约）、ADR-0005（组合根三职责不变）
- Keeps: ADR-0029（封闭对象图、无构造后 bind/install）
- 守护测试：`tests/test_spec_composition.py`、
  `tests/test_refactor_guards.py`（无全局单例 / 无封闭图挖掘）
