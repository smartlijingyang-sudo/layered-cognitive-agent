"""FactoryResolver — yaml `factory:` 业务语义名 → NodeExecutor 实例。

ADR-0217 §3.1。

三级解析规则,顺序命中即返回,都不命中 fail-loud:
1. `(semantic_name, region)` 二元组精确匹配 `NodeExecutor.semantic_name`。
2. `(semantic_name, None)` 兜底匹配(plugin 注册时 region 可为 None)。
3. 抛 `FactoryResolutionError`(PG-005-factory),不静默 fallback。

为什么两级、不读 plugin_id:业务 yaml 永远不知道 plugin 长什么样;plugin 重命名
/ 命名空间调整 / 拆分合并都不影响 yaml。

注册表维护:`register()` 由 think 子图 plugin 的 `@plugin(...)` 装饰器在
setup 期调用,放入进程级 dict。不走全局 context / magic — setup 阶段结束
即冻结,运行时只读。

职责边界:
- 本模块**只**做注册 + 解析,不解析 yaml、不构造 CompiledRunPlan、不装配
  NodeContext。这些职责在 `lca.harness.declarative.compile.subgraph_resolver`
  与 `lca.harness.graph.execute.interpreter`。
"""

from __future__ import annotations

from threading import RLock
from typing import Iterable

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeExecutor,
)


class FactoryResolutionError(DeclarativeValidationError):
    """Factory 字符串解析到 NodeExecutor 失败。

    错误码 PG-005-factory。fail-loud,不静默 fallback。
    """

    def __init__(self, factory: str, region: str | None) -> None:
        super().__init__(
            "PG-005-factory",
            f"no NodeExecutor found for factory={factory!r} region={region!r}",
        )
        self.factory = factory
        self.region = region


class FactoryRegistry:
    """NodeExecutor 进程级注册表。

    线程安全:写者(plugin setup 期)在 register 互斥下登记;读者(interpreter
    编译期)在 resolve 时不加锁(因为 dict 在 CPython 下原子读)。
    """

    def __init__(self) -> None:
        self._by_semantic: dict[tuple[str, str | None], NodeExecutor] = {}
        self._lock = RLock()

    def register(
        self,
        executor: NodeExecutor,
        *,
        semantic_name: str,
        region: str | None,
    ) -> None:
        """注册一个 NodeExecutor 实例。重复 semantic_name 抛 ValueError。"""
        key = (semantic_name, region)
        with self._lock:
            if key in self._by_semantic:
                raise ValueError(
                    f"duplicate NodeExecutor registration: "
                    f"semantic_name={semantic_name!r} region={region!r}"
                )
            self._by_semantic[key] = executor

    def resolve(self, factory: str, region: str | None) -> NodeExecutor:
        """三级解析 factory → NodeExecutor。都不命中抛 FactoryResolutionError。

        规则 1:`(factory, region)` 精确匹配。
        规则 2:`(factory, None)` 兜底匹配(plugin 注册时可省略 region)。
        """
        if not factory:
            raise FactoryResolutionError(factory, region)

        executor = self._by_semantic.get((factory, region))
        if executor is not None:
            return executor

        executor = self._by_semantic.get((factory, None))
        if executor is not None:
            return executor

        raise FactoryResolutionError(factory, region)

    def all(self) -> Iterable[NodeExecutor]:
        return tuple(self._by_semantic.values())

    def __len__(self) -> int:
        return len(self._by_semantic)


# 进程级单例。`@plugin(...)` 装饰器在 setup 阶段调用 `_default_registry.register`。
_default_registry = FactoryRegistry()


def get_default_registry() -> FactoryRegistry:
    """返回进程级默认注册表。"""
    return _default_registry


__all__ = [
    "FactoryRegistry",
    "FactoryResolutionError",
    "get_default_registry",
]
