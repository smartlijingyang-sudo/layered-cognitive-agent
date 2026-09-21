# Agent Note: 执行环境投影补齐闭集并携带能力摘要

Status: implemented

## Problem

`ExecutionEnvironment` 是从 `PlaneRef` 与设备注册表派生的模型可见投影。修复前它有两处断裂。

第一,`EnvironmentKind` 只有 sandbox、machine、ssh 三个成员,而 `PlaneKind` 已有
`POOL_WORKER`(ADR-0246 M1)。`environment_from_plane` 直接写
`EnvironmentKind(plane.kind.value)`,对 pool_worker 平面投影时抛
`ValueError: 'pool_worker' is not a valid EnvironmentKind`,任何带 pool_worker 的
run 在渲染环境目录时都会崩溃。

第二,`ExecutionEnvironment.capabilities` 字段已声明并在 `to_dict` 中序列化,但两条构造
路径都不填充:`environment_from_plane` 丢弃了 `PlaneRef.capability_summary`,设备投影
也不读设备 payload。`listEnvironments` 永远对每台机器报告空能力列表,模型无法据此判断
目标机器能做什么。

## Decision

`EnvironmentKind` 增加 `POOL_WORKER = "pool_worker"` 成员,与 `PlaneKind` 对齐。闭集现在
包含 `PlaneKind` 的全部成员,`SSH` 保留为设备目录可能先于平面存在的超前成员。

`environment_from_plane` 把 `plane.capability_summary` 投影为 `capabilities`。
`DeviceEnvironmentProvider._from_device` 用设备工作目录填充 `root` 与 `outputs_dir`
(与 `plane_ref_for_device` 的语义一致),并从设备 payload 的 `capabilities` 字段投影能力列表。

两条投影路径现在对同一台机器给出同一组字段,不再各填一半。

## Alternatives considered

### Why not 在 `environment_from_plane` 里把 pool_worker 过滤掉或映射成 machine?

过滤会隐藏真实存在的执行平面,模型看不到团队 worker。映射成 machine 会伪造环境种类,
违反 I-UMS-5 的区分要求。给 `EnvironmentKind` 加 `POOL_WORKER` 是与 `PlaneKind` 唯一
忠实的对齐。

### Why not 让 `capabilities` 从别处推导(如权限清单)?

`PlaneRef.capability_summary` 已经是 ADR-0246 M1 为平面携带的能力摘要,投影直接读取它
是单向依赖。重新推导会产生第二真值。

### Why not 维持现状?

pool_worker 投影会在运行时抛 `ValueError`,`listEnvironments` 对机器返回空能力,模型拿到
残缺的环境画像。维持现状的成本是每次遇到 worker 平面都崩溃。

## Consequences

`EnvironmentKind` 是 `PlaneKind` 的超集。`SSH` 仍是超前成员,`PlaneKind` 尚无对应值。
新增成员是向后兼容的:只有 pool_worker 平面的环境会带上新 kind,现有 wire 形状不变。

设备投影现在报告与平面投影一致的 `root`、`outputs_dir`、`workspace` 与 `capabilities`,
`to_dict` 的 wire 形状保持稳定。

## Verification

`tests/contracts/models/environment/test_execution_environment.py` 新增 pool_worker 投影
与 capabilities 投影测试。`tests/infrastructure/environment/test_environment_catalog.py`
的设备行断言扩展了 `root`、`outputs_dir`、`capabilities`。环境目录、感知工具、计算机工具、
run 冒烟相关测试全部通过。`tests/plugins/state` 的收集错误在干净 HEAD 上原样复现,不是
本次引入。