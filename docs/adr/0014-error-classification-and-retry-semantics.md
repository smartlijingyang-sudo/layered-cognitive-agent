---
title: ADR-0014: 工具错误分类与重试语义
status: Accepted
date: 2026-07-28
---

# ADR-0014: 工具错误分类与重试语义

## 状态

Accepted

## 背景

`CalculatorTool` 在 LLM 生成空表达式 `""` 时，`ast.parse("")` 抛出 `SyntaxError`，被 `SafeExecutor` 的重试循环捕获后以指数退避重试 3 次（~7 秒），每次输入完全相同，结果必然相同。

这不是 calculator 独有的问题——任何新工具（weather_tool、search_tool 等）遇到参数缺失或类型错误时，都会陷入同样的"无效重试"陷阱。根本原因是系统缺少两个通用机制：

1. **错误分类协议**：`ToolExecutionError` 把所有失败归为一类，SafeExecutor 无法区分"网络超时（重试可能恢复）"和"表达式为空（重试不会改变结果）"
2. **统一校验钩子**：工具的参数校验要么不做，要么各自为政地在 `execute()` 内部处理，SafeExecutor 无法在执行前拦截明显的非法输入

## 决定

### 1. 错误自带 `retryable` 信号

`ToolExecutionError` 基类增加 `retryable: bool = True` 类属性。新增子类 `ToolInputError(ToolExecutionError)`，`retryable = False`。

SafeExecutor 的重试循环捕获 `ToolExecutionError` 时读取 `getattr(err, "retryable", True)`：
- `True`：维持现有指数退避重试行为
- `False`：立即返回失败 Observation，不 sleep、不消耗 attempt 配额

**谁负责声明**：抛出异常的一方。工具内部如果错误是确定性的（参数非法、语法错误），必须抛 `ToolInputError` 而不是裸 `ValueError`/`SyntaxError`。SafeExecutor 不做错误分类猜测。

### 2. Tool 协议增加可选 `validate` 钩子

```python
def validate(self, args: dict[str, Any]) -> str | None:
    """返回 None = 合法，返回字符串 = 错误信息。"""
```

- 可选方法，通过 `hasattr` / `getattr` 检查，未实现的工具跳过校验
- SafeExecutor 在重试循环**之前**调用，校验失败直接构造 `Observation(success=False, extra={"failure_kind": "validation"})`，根本不进入 for 循环
- 谁的参数谁校验——CalculatorTool 自己声明 "expression 不能为空"，而不是让 DecisionParser 去认识每个工具的私有参数结构

### 3. `failure_kind` 可观测性字段

`Observation.extra["failure_kind"]` 取值：
- `"validation"`：validate 钩子拦截
- `"execution"`：工具 execute 内部返回失败或抛出 ToolExecutionError
- `"transient"`：非 ToolExecutionError 的意外异常（网络错误等）

Critic（`SimpleCritic`）读取 `failure_kind` 生成差异化纠正提示：
- `validation` → "参数不合法，须修正参数后重新调用"
- `transient` → "瞬时性错误，可重试"
- `execution` → "工具执行失败"（默认）

### 4. SafeExecutor 单一分流点

SafeExecutor 的重试决策只依赖两个信号，不认识任何具体工具或参数：
1. `tool.validate(args)` 的返回值
2. 异常的 `retryable` 属性

这保证了新增工具时 SafeExecutor 无需修改。

## 后果

### 正面
- **calculator 的空表达式问题自动解决**：validate 拦截空输入，不进入重试循环
- **语法错误（如 `"2+"`）也覆盖**：`ast.parse` 的 `SyntaxError` 包装为 `ToolInputError`，SafeExecutor 读 `retryable=False` 立即返回
- **新工具自动受益**：只要实现 `validate` 和/或抛 `ToolInputError`，就获得正确的重试语义
- **Critic 纠正提示更精确**：LLM 收到"参数不合法"而不是笼统的"失败了再试"
- **契约测试兜底**：`tests/contract/test_tool_error_classification.py` 验证所有注册工具的非法输入不触发 `asyncio.sleep`

### 风险
- `Tool` Protocol 新增 `validate` 方法可能影响现有自定义工具的 `isinstance` 检查——但 `@runtime_checkable` Protocol 只检查属性存在性，新增带默认实现的方法不会破坏现有工具
- `failure_kind` 是 `extra` 字典中的可选字段，不改变 `Observation` 的 dataclass 签名，向后兼容

## 工具开发者清单

新增工具时必须遵守：

1. **参数存在必填/格式约束** → 实现 `validate(args) -> str | None`
2. **工具内部会抛出确定性错误**（语法错误、类型错误、业务规则违反） → 用 `ToolInputError` 而不是裸 `ValueError`/`SyntaxError`
3. **瞬时性错误**（网络超时、API 限流） → 保持现有行为，SafeExecutor 默认重试

不写 `validate` 不会导致编译错误，但校验缺位会在契约测试中以"重试了不该重试的错误"的形式暴露。
