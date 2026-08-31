# lca.plugins.creator

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 1.0.0

## 1. 职责
Creator 模式插件 —— 提供 persona 库实现，让 Agent 在创建时选用合适的 persona profile。

## 2. 不负责
- Persona 数据定义（由 personas/ 子目录提供）
- 运行时 persona 注入（由 Brain / Profile 装配期决定）

## 3. 输入
- Persona id（string）
- 可选 traits dict

## 4. 输出
- `personas/implementations.py` 提供 `lca-creator-personas-default` —— 标准 persona 实现

## 5. 允许依赖
lca.contracts, lca.plugins

## 6. 禁止依赖
gateway

## 7. 副作用
log:emit

## 8. 失败语义
- 未知 persona id → CreatorError
- Persona schema 校验失败 → 装载期拒绝

## 9. 公共入口
- `personas`