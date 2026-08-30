# gateway/device_gateway

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `9` 个公开模块 + `65` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：8 个显式 __all__ 条目； 65 个定义符号中，50 个为公共命名

## 5. 允许依赖
—

## 6. 禁止依赖
—

## 7. 副作用
log:emit

## 8. 失败语义
模块导入失败 → ImportError；类实例化失败 → TypeError / ValueError；运行时错误以 L1 protocol 中定义的异常类型抛出。

## 9. 公共入口
**__init__.py 显式 __all__**:

- `AuthError`
- `AuthenticatedUser`
- `Device`
- `DeviceConnection`
- `DeviceGatewaySettings`
- `DeviceHub`
- `DeviceRegistry`
- `verify_token`

**模块清单**:

- `gateway/device_gateway/auth.py`
- `gateway/device_gateway/bind.py`
- `gateway/device_gateway/hub.py`
- `gateway/device_gateway/models.py`
- `gateway/device_gateway/registry.py`
- `gateway/device_gateway/routes.py`
- `gateway/device_gateway/settings.py`
- `gateway/device_gateway/streaming_dsh_runtime.py`
- `gateway/device_gateway/transport.py`
