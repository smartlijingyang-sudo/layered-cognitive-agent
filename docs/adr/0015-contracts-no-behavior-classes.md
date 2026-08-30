# ADR-0015: contracts/ 仅保留类型与接口，参考实现必须放在实现层

## 状态
Accepted

## 背景
`DelegationLedger`（`DelegationLedgerProtocol` 的默认实现）曾与 Protocol 定义放在同一个文件 `lca/contracts/team_progress.py` 中。这导致：

1. **L3 越权实例化**：`HierarchicalStrategy` 直接从 contracts import 了具体类并 `DelegationLedger(...)` 实例化，完全绕开了 L4 组装根（ADR-0005）。
2. **分层检测盲区**：现有 import-linter 只检查"层与层"粒度，而 contracts 层被所有层依赖是合法的，因此"契约 vs 实现"混在同一模块内的违规无法被自动检测。
3. **诱导性架构违规**：Protocol 和实现挤在同一个 import 路径下，写代码时"顺手用具体类"比"坚持依赖倒置"更省力，文件组织方式诱导了违规。

## 决定

### 物理拆分
- `lca/contracts/team_progress.py` 只保留 `RoleStatus`、`DelegationLedgerProtocol` 以及仅依赖 Protocol 的 hook 函数。
- `DelegationLedger`（具体 frozen dataclass 实现）迁到 `lca/cognition/team_progress/delegation_ledger.py`，与 Brain/Body/Memory 平级。

### 依赖注入
- `OrchestrationContext` 新增 `ledger_factory: Callable[[frozenset[str]], DelegationLedgerProtocol] | None` 字段。
- `HierarchicalStrategy` 不再 import 具体类，改为 `context.ledger_factory or _default_ledger_factory`，默认工厂通过 `ComponentRegistry.resolve("delegation_ledger", "default")` 从全局注册表获取。
- `application/defaults.py` 注册 `DelegationLedger`：`reg.register("delegation_ledger", "default", DelegationLedger)`。

### 门禁机制
- 新增 `tests/test_contracts_purity.py`：AST 扫描 `lca/contracts/` 下所有类，非 Protocol 类必须是 `@dataclass` 且不含除 `__post_init__` / dunder 外的自定义方法。
- 物理拆分后，若 L3 再 import L1 具体类，现有 import-linter 的 `layers` 契约即可自动检测到。

## 适用范围
- contracts/ 内如需同时定义 Protocol 与其参考实现，参考实现必须放在对应实现层（L0-L1），contracts/ 仅保留类型与接口。
- 所有具体实现的实例化必须经过 L4 组装根（`defaults.py`）或显式依赖注入，L0-L3 不得自行实例化。

## 放弃的方案
- **在 contracts/ 内保留实现但加 lint 规则**：需要新写检测逻辑，且违规仍是"同模块内的语义边界"，不如物理拆分后让现有层间规则自动覆盖来得省心。
- **把 hooks 也迁到 L1**：hooks 仅依赖 Protocol（`DelegationLedgerProtocol`），不依赖具体实现，留在 contracts/ 不违反纯净性，且 L3 可直接 import。

## 后果
- 正面：
  - 现成 import-linter 层间规则自动覆盖"具体类跨层引用"，不需要额外检测逻辑。
  - "零配置三行代码创建 Agent"体验不受影响（默认工厂已注册）。
  - 可替换性补齐：用户可注册自己的 ledger 实现或传入自定义 `ledger_factory`。
- 负面：
  - 多了一层间接（注册表解析），调试时需要理解注册表链路。
  - `OrchestrationContext` 新增字段增加了认知负担，但 `None` 默认值保证向后兼容。
