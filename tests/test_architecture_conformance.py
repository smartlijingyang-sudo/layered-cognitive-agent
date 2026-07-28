"""架构一致性元测试 —— 确保 L0-L3 每个具体类都显式声明了 Protocol 基类。

不再逐个手动列举实现类，而是扫描 L0-L3 所有模块，枚举每一个具体类，
断言它要么显式声明了 contracts.protocols 里的某个 Protocol 作为基类，
要么在 EXEMPT 白名单中注明了 ADR 依据。

"默认拒绝"——新类不声明协议就直接挂在 CI 上，不依赖任何人"记得"。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import unittest

# ── 豁免清单 ──────────────────────────────────────────────────────────
# 键: 类的全限定名 (qualname)
# 值: 豁免理由（必须引用 ADR 编号）
#
# 豁免标准（详见 ADR-0010）：
#   1. DI 注册表 / 路由基础设施——它们是协议接线机制本身，不是被接线的组件
#   2. 内部数据结构——不跨越模块边界、不需要运行时多态
#   3. 异常类型——错误信号，不是可插拔组件
EXEMPT: dict[str, str] = {
    "lca.layer0_infra.registry.ComponentRegistry": (
        "DI 注册表本身，非可插拔组件 (ADR-0005/ADR-0010)"
    ),
    "lca.layer0_infra.registry.RegistryKeyError": ("异常类型，非可插拔组件 (ADR-0010)"),
    "lca.layer0_infra.transport.transport_registry.TransportNotFoundError": (
        "异常类型，非可插拔组件 (ADR-0010)"
    ),
    "lca.layer1_cognitive.body.action_handlers.RespondHandler": (
        "ActionHandler 策略实现，Protocol 定义在 contracts.action 而非 contracts.protocols"
    ),
    "lca.layer1_cognitive.body.action_handlers.UseToolHandler": (
        "ActionHandler 策略实现，Protocol 定义在 contracts.action 而非 contracts.protocols"
    ),
    "lca.layer1_cognitive.body.action_handlers.DelegateHandler": (
        "ActionHandler 策略实现，Protocol 定义在 contracts.action 而非 contracts.protocols"
    ),
    "lca.layer1_cognitive.body.action_handlers.HandoffHandler": (
        "ActionHandler 策略实现，Protocol 定义在 contracts.action 而非 contracts.protocols"
    ),
    "lca.layer2_runtime.fallback_handler.FallbackActionHandler": (
        "韧性层降级处理器，Chain-of-Responsibility 兜底节点，非 ActionHandler Protocol 实现"
    ),
}

_SCAN_PACKAGES = [
    "lca.layer0_infra",
    "lca.layer1_cognitive",
    "lca.layer2_runtime",
    "lca.layer3_agent",
]


def _collect_protocol_classes() -> set[type]:
    """收集 lca.contracts.protocols 中所有 Protocol 类。

    利用 typing 模块对 Protocol 子类设置的 _is_protocol 标记，
    只匹配直接继承 Protocol 的接口定义，不会误匹配实现了 Protocol 的具体类。
    """
    import lca.contracts.protocols as protocols_mod

    result: set[type] = set()
    for _name, obj in inspect.getmembers(protocols_mod, inspect.isclass):
        if obj.__module__ == protocols_mod.__name__ and getattr(obj, "_is_protocol", False):
            result.add(obj)
    return result


def _collect_concrete_classes() -> dict[str, type]:
    """扫描 L0-L3 所有模块，收集其中定义的公开具体类。

    通过 cls.__module__ 过滤，确保只收录"定义在"目标包中的类，
    排除从 contracts 或其他包 import 进来的类。
    """
    result: dict[str, type] = {}
    for pkg_name in _SCAN_PACKAGES:
        pkg = importlib.import_module(pkg_name)
        for _importer, modname, _ispkg in pkgutil.walk_packages(
            pkg.__path__,
            prefix=pkg.__name__ + ".",
        ):
            try:
                mod = importlib.import_module(modname)
            except ImportError:
                continue
            for _cls_name, cls in inspect.getmembers(mod, inspect.isclass):
                if not cls.__module__.startswith(pkg_name):
                    continue
                qualname = f"{cls.__module__}.{cls.__qualname__}"
                result[qualname] = cls
    return result


class TestArchitectureConformance(unittest.TestCase):
    """L0-L3 每个具体类必须显式声明 Protocol 基类，否则必须出现在 EXEMPT 中。"""

    def test_protocol_count_regression(self) -> None:
        """回归防护：Protocol 数量不得低于当前基线（32 个），防止重构意外删除协议。"""
        protocol_bases = _collect_protocol_classes()
        self.assertGreaterEqual(
            len(protocol_bases),
            32,
            "Protocol 数量低于基线 32 —— 是否有协议被意外删除？"
            " 如果确实需要减少协议数量，请同步更新此断言并附 ADR。",
        )

    def test_every_l0_to_l3_class_declares_a_protocol(self) -> None:
        protocol_bases = _collect_protocol_classes()
        self.assertGreater(
            len(protocol_bases),
            0,
            "contracts.protocols 中未找到任何 Protocol 类——扫描逻辑可能有误",
        )

        concrete_classes = _collect_concrete_classes()
        self.assertGreater(
            len(concrete_classes),
            0,
            "L0-L3 未扫描到任何具体类——包路径或扫描逻辑可能有误",
        )

        offenders: list[str] = []
        for qualname, cls in sorted(concrete_classes.items()):
            if qualname in EXEMPT:
                continue
            if getattr(cls, "_is_protocol", False):
                continue
            if set(cls.__mro__) & protocol_bases:
                continue
            offenders.append(qualname)

        self.assertFalse(
            offenders,
            "以下类未声明任何 Protocol 且未在 EXEMPT 中注明理由：\n"
            + "\n".join(f"  - {q}" for q in offenders),
        )

    def test_exempt_entries_are_accurate(self) -> None:
        """EXEMPT 中的每个条目必须指向真实存在的类，防止白名单腐烂。"""
        concrete_classes = _collect_concrete_classes()
        stale = [qualname for qualname in EXEMPT if qualname not in concrete_classes]
        self.assertFalse(
            stale,
            "EXEMPT 中包含不存在的类（已删除或重命名），请清理：\n"
            + "\n".join(f"  - {q}" for q in stale),
        )


if __name__ == "__main__":
    unittest.main()
