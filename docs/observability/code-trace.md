# Code Trace — ADR-0065 §五

## 受控 instrumentation(非热路径)

0065 §五 显式否决自动 `inspect.stack()` 采集:
- 热路径开销(每次 emit 5-15μs)
- 泄露部署路径
- 不能提供稳定的构建级可重现定位

## 何时记录 SourceLocation

仅在以下场景受控 instrumentation:
- 错误诊断(only on failure path)
- Crash dump
- 按需手工 trace(显式 API 调用)

字段:
- `build_revision`(构建 hash,非部署路径)
- `module`(模块名)
- `symbol`(符号)
- `line`(可选行号)

## 数据流

SourceLocation 显式 emit → `RuntimeObserved(kind="code", operation="code.execution")`,
分类为诊断数据;不作为账本默认字段。