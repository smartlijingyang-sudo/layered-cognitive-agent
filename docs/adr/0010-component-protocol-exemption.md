# ADR-0010: 组件协议豁免规则

## 状态
Accepted

## 背景
框架的 Protocol-First 设计（ADR-0004）要求所有可插拔组件显式声明 Protocol 基类。但并非所有类都需要协议：有些类是 DI 基础设施本身，有些是 L4 终端门面。如果不在文档中明确"什么时候可以不声明 Protocol"，贡献者只能靠读代码猜测，容易把例外用错地方。

同时，`test_architecture_conformance.py` 维护了一个机器可执行的豁免清单（`EXEMPT` 字典），需要与文档保持同步。

## 决定

### 默认规则
L0-L3 任何具体类都**必须**显式声明 `lca.contracts.protocols` 中的某个 Protocol 作为基类。不声明 = CI 报错（`test_every_l0_to_l3_class_declares_a_protocol`）。

### 两类豁免

**1. L4 门面类**（`Agent` / `MultiAgentTeam`）
它们是组合根的终端消费者，没有更上层需要通过 Protocol 替换它们（ADR-0001、ADR-0005）。L4 整体不在扫描范围内。

**2. DI 基础设施类**
| 类 | 理由 |
|---|---|
| `ComponentRegistry` | DI 注册表本身，是协议接线机制，不是被接线的组件 |
| `StrategyRegistry` | 同上 |
| `OrchestrationStrategyRegistry` | 编排策略注册表，同上 |
| `TransportRegistry` | 传输路由基础设施，同上 |
| `TeamSharedMemoryStore` | 跨 Agent 共享记忆数据存储，不需要 Protocol 多态 |
| `TransportNotFoundError` | 异常类型，非可插拔组件 |

### 新增豁免的流程
1. 在 `tests/test_architecture_conformance.py` 的 `EXEMPT` 字典中添加条目，值必须引用 ADR 编号
2. 新建或修订一篇 ADR，写明豁免理由
3. 两者必须同步——CI 的 `test_exempt_entries_are_accurate` 会检测过期的白名单条目

## 自动化保障

| 机制 | 作用 |
|---|---|
| `test_every_l0_to_l3_class_declares_a_protocol` | 默认拒绝：新类不声明协议 → CI 红 |
| `test_exempt_entries_are_accurate` | 防止白名单腐烂：已删除/重命名的类仍在 EXEMPT 中 → CI 红 |
| `mypy` (pre-commit + CI) | 组合根以协议类型持有实现 → 签名不兼容时提交报错 |

## 放弃的方案
- **结构化 isinstance 自动检测（不要求显式继承）**：很多 Protocol 带数据属性，对未实例化的类做 `issubclass` 在 PEP 544 下会报错；实例化又需要各类的构造依赖，自动化成本很高。显式声明检查复用代码库已有的约定，零误报。
- **完全自动化、零白名单**：无法区分"故意不声明"和"忘记声明"，会产生大量误报。

## 后果
- 正面："忘记给新组件声明协议"从"依赖 code review 人肉发现"变成"CI 结构性拦截"。
- 负面：新增豁免需要同时改代码和写 ADR，但这个摩擦本身就是有价值的——它迫使团队认真思考"这个类到底需不需要可替换"。
