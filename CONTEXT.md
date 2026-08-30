# LCA 领域词汇表

## Profile 启动产物

**Profile 启动产物**是一次 Profile 启动完成后可供后续路径读取的不可变事实对：**解析 Profile** 描述已验证的插件声明、依赖图和配置来源；**编译运行计划**描述由该声明唯一导出的可执行运行闭包。二者必须在同一启动过程内产生，并通过单一接缝供组合、运行和诊断读取；调用方不得重新编译、从 Context 动态属性猜测其名称，或将两次启动的产物混用。检查视图由解析 Profile 派生，诊断与生命周期不得再读取平行的 `Context.entries`。

## 程序化 Profile 输入

**程序化 Profile 输入**是 `boot_entries()` 接收的内存插件声明。它仅是对文件 Profile 的输入适配：保留调用方声明顺序和来源、规范化历史 `config.disabled` 写法，然后交给与 YAML Profile 相同的 Resolve 模块。它不得拥有第二套 Manifest 身份、配置校验、provider 所有权、层级或 DAG 语义；运行时闭合仍由其显式测试夹具按既有能力读取路径验证。程序化入口同样经启动产物接缝附加解析 Profile，但不编译运行计划。

## StopPolicy

**StopPolicy** 是 State 群提供给固定 `stop` 阶段的局部终止策略。它从 `AgentState`、本轮 `Decision`、`Observation` 与 `Reflection` 派生 `StopDecision`，并可使用已注入的 artifact closure 形成终态输出。它不是 AgentSpec 选择轴、注册表、AgentGraph 事实或 CognitiveRuntime 的顶层依赖；替换只通过 Profile 选择 State 群 Provider 完成。
