"""EventRegistry 鉴权矩阵 SSOT 后置校验(ADR-0181+1)。

锁住两条契约:
- :meth:`EventRegistry.validate_publisher_authorization`:
  yaml ``publishers`` token 必须在 catalog(id-form) 或 class-path 中
  解析得到 type。任一 miss → :class:`UnknownPluginIdError`。
- :meth:`EventRegistry.check_manifest_emits_aligned`:
  ``OwnershipDeclaration.emits`` 的每条 execution_point 必须是已登记
  category,且对应 plugin id 在该 category 的 publishers 集合中。
  任一未授权 → :class:`AuthMatrixMismatchError`。

回归覆盖(2026-09-04 web-standard 500):yaml publishers 用了下划线短
形式(``events.spine_reflector_X``)但 plugin manifest id 是点分
(``events.spine.reflector.X``)→ 静默退化为空 publishers 集合 →
首次请求 500。本测试确保 boot 期 fail-fast,信息含 category+token。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca_kernel.events.errors import AuthMatrixMismatchError, UnknownPluginIdError
from lca_kernel.events.registry import EventRegistry


def _config_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "lca_kernel" / "events" / "config"


def test_validate_publisher_authorization_passes_with_aligned_catalog() -> None:
    """catalog 与 yaml 现状对齐(2026-09-04 web-standard)→ validate 通过。

    真实 boot 路径会注入 16 个 publisher(13 个 spine_reflector_X + delegation_cache
    + spine_loop_cursor + spine_writable_matrix)。此测试用同一份 catalog
    注入,验证 :meth:`validate_publisher_authorization` 不抛。
    """
    from lca_kernel.events.test_catalog import build_test_catalog

    config_dir = _config_dir()
    catalog = build_test_catalog()
    registry = EventRegistry.load(config_dir, catalog=catalog)
    registry.refresh()
    # 不应抛
    registry.validate_publisher_authorization()


def test_validate_publisher_authorization_fails_with_empty_catalog() -> None:
    """catalog 缺位(catalog={})→ 大量 token miss → fail-fast。

    锁住"任何 token miss 必须升级为 UnknownPluginIdError,不能静默退化
    为空 publishers 集合"(2026-09-04 根因)。
    """
    registry = EventRegistry.load(_config_dir(), catalog={})
    registry.refresh()
    with pytest.raises(UnknownPluginIdError) as ei:
        registry.validate_publisher_authorization()
    msg = str(ei.value)
    # 错误信息必须可定位:含 "event-bus-yaml" 源 + 失败计数 + 至少一个 token
    assert "event-bus-yaml" in msg
    assert "失败" in msg or "失败" in repr(ei.value)
    # plugin_id 字段记录了第一个 miss token
    assert ei.value.plugin_id


def test_validate_publisher_authorization_drift_message_includes_token() -> None:
    """Drift 信息含具体 token,运营可据此定位 yaml 错位行。"""
    from lca_kernel.events.test_catalog import build_test_catalog

    # 拿掉一个 reflector 的 catalog 项,模拟"yaml 引用了但 plugin 没启"
    catalog = build_test_catalog()
    catalog.pop("events.spine.reflector.transport", None)
    registry = EventRegistry.load(_config_dir(), catalog=catalog)
    registry.refresh()
    with pytest.raises(UnknownPluginIdError) as ei:
        registry.validate_publisher_authorization()
    # 错误源标记是 event-bus-yaml 而非 plugin id 解析(后者也是同一类异常,
    # 但 source 字段不同)
    assert "event-bus-yaml" in ei.value.source


def test_check_manifest_emits_aligned_passes_for_known_publisher() -> None:
    """plugin 声明的 emits 都是已登记 category 且 plugin 在 publishers 集合 → 通过。"""
    from lca_kernel.events.test_catalog import build_test_catalog

    catalog = build_test_catalog()
    registry = EventRegistry.load(_config_dir(), catalog=catalog)
    registry.refresh()
    # transport reflector 声明的 6 个 emit 全是已登记 category
    emits = (
        "spine.transport.route.enter",
        "spine.transport.route.exit",
        "spine.transport.sse.publish",
        "spine.kernel.run.start",
        "spine.kernel.run.stop",
        "spine.kernel.run.cancelled",
    )
    # 不应抛
    registry.check_manifest_emits_aligned("events.spine.reflector.transport", emits)


def test_check_manifest_emits_aligned_fails_for_unknown_execution_point() -> None:
    """plugin emits 包含未登记的 execution_point → AuthMatrixMismatchError。"""
    from lca_kernel.events.test_catalog import build_test_catalog

    catalog = build_test_catalog()
    registry = EventRegistry.load(_config_dir(), catalog=catalog)
    registry.refresh()
    with pytest.raises(AuthMatrixMismatchError) as ei:
        registry.check_manifest_emits_aligned(
            "events.spine.reflector.transport",
            ("spine.transport.route.enter", "spine.does.not.exist"),
        )
    assert "spine.does.not.exist" in ei.value.missing_publish


def test_check_manifest_emits_aligned_fails_for_emits_not_in_publishers() -> None:
    """plugin 用了别的 plugin 授权的 category(自己不在 publishers 集合)→ fail。"""
    from lca_kernel.events.test_catalog import build_test_catalog

    catalog = build_test_catalog()
    registry = EventRegistry.load(_config_dir(), catalog=catalog)
    registry.refresh()
    # spine_reflector_transport 试图 publish cognition category,自己不在该集合
    with pytest.raises(AuthMatrixMismatchError):
        registry.check_manifest_emits_aligned(
            "events.spine.reflector.transport",
            ("spine.cognition.brain.perceive.start",),
        )


def test_check_manifest_emits_aligned_passes_for_empty_emits() -> None:
    """emits 为空(未声明)→ 不抛(向后兼容:不强制每个 plugin 都声明 emits)。"""
    from lca_kernel.events.test_catalog import build_test_catalog

    catalog = build_test_catalog()
    registry = EventRegistry.load(_config_dir(), catalog=catalog)
    registry.refresh()
    # 不应抛
    registry.check_manifest_emits_aligned("events.spine.reflector.transport", ())
