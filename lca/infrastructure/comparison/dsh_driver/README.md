# lca/infrastructure/comparison/dsh_driver

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 2.0.0

## 1. 职责
LCA 框架的组成部分。具体职责参见同目录下各子包的 README 与 pyproject.toml 中的 ``[tool.lca.package_contracts]`` 块。

## 2. 不负责
与下层契约的合规性检查（由 lint-imports 与 check_package_contracts 门禁统一处理）；任何不在本目录 schema_version 范围内的修改都不应提交。

## 3. 输入
- 当前包内 `18` 个公开模块 + `80` 个公开符号（class / function）

## 4. 输出
- 暴露的公共 API：8 个显式 __all__ 条目； 80 个定义符号中，42 个为公共命名

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

- `DshNotification`
- `DshSettings`
- `DshTurnDriver`
- `DshTurnResult`
- `DshTurnSpec`
- `compose_dsh_prompt`
- `is_dsh_driver`
- `run_dsh_machine_turn`

**模块清单**:

- `lca/infrastructure/comparison/dsh_driver/archive.py`
- `lca/infrastructure/comparison/dsh_driver/daemon_worker.py`
- `lca/infrastructure/comparison/dsh_driver/driver.py`
- `lca/infrastructure/comparison/dsh_driver/harvest.py`
- `lca/infrastructure/comparison/dsh_driver/launch.py`
- `lca/infrastructure/comparison/dsh_driver/machine_runtime.py`
- `lca/infrastructure/comparison/dsh_driver/mapping.py`
- `lca/infrastructure/comparison/dsh_driver/models.py`
- `lca/infrastructure/comparison/dsh_driver/ports.py`
- `lca/infrastructure/comparison/dsh_driver/projector.py`
- `lca/infrastructure/comparison/dsh_driver/prompt.py`
- `lca/infrastructure/comparison/dsh_driver/routing.py`
- `lca/infrastructure/comparison/dsh_driver/run.py`
- `lca/infrastructure/comparison/dsh_driver/runtime.py`
- `lca/infrastructure/comparison/dsh_driver/settings.py`
- `lca/infrastructure/comparison/dsh_driver/sink.py`
- `lca/infrastructure/comparison/dsh_driver/stream_params.py`
- `lca/infrastructure/comparison/dsh_driver/wire.py`
