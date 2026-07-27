## Code Review Checklist

### 分层
- [ ] 新增代码是否只通过 `Runtime.configure()` / Protocol 方法与其它层通信？
- [ ] 新增跨 Agent / 跨进程传递的数据是否已在 `contracts/` 定义为 DTO？

### 目录
- [ ] 新文件是否超过 250 行？如果是，是否已拆分或登记豁免理由？

### 类设计
- [ ] 新类的所有公开方法是否能用一句不含"和/并且"的话描述？
- [ ] 是否存在两个方法有 > 50% 重复逻辑本该提取为私有方法？

### 函数
- [ ] 新增/修改的函数是否用 if/elif 链处理 ≥ 3 个分支？是否应改为分发表？

### 命名
- [ ] 是否引入了 `Manager/Util/Helper/Handler/Processor/Advanced` 等禁用词？（豁免须在 `docs/glossary.md` 登记）
- [ ] 是否引入了新领域术语但未同步更新 `docs/glossary.md`？

### 协议
- [ ] 新的可插拔组件是否显式声明了 Protocol 基类，或在 `EXEMPT` 中登记了 ADR 依据？

### ADR
- [ ] 本次改动是否触及"层职责边界""新增编排模式""放弃某个设计方案"？如果是，是否已配套新 ADR？

### 测试
- [ ] 新增的 `OrchestrationStrategy` / `BrainStrategy` 实现是否有对应的黄金轨迹测试？

### 诚实注释
- [ ] 如果是"最小实现"（`Simple*` 占位），docstring 是否显式声明了能力边界？
