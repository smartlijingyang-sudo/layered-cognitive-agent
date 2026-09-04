"""Parity tests ported from dsh/packages/core/session/src/request-header.ts.

Source: deepseek-harness ``packages/core/session/tests/request-header.spec.ts``.

每个 fixture 直接 mirror dsh 测试用例:

- ``canonicalHeader`` —— normalizes empty optional fields / preserves populated
- ``headerEquals`` —— compares every canonical field / preserves tool order
- ``headerEquals`` —— treats absent and empty tool arrays as equivalent
- ``foldRequestHeader`` —— returns the supplied baseline when no snapshot follows
- ``foldRequestHeader`` —— takes the latest full snapshot and skips unrelated events

任何字段级差异要在 PR body 显式说明(ADR-0185 PR-0 验收条目)。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca_kernel.events.fold import (
    EpochHeader,
    canonicalHeader,
    foldRequestHeader,
    headerEquals,
)

CONFIG: dict[str, Any] = {"provider": "mock", "model": "m"}


def tool(name: str, description: str = "d") -> dict[str, Any]:
    """Mirror dsh ``tool(name, description)`` 工厂:tools 是 dict 而非 TS object。"""
    return {"name": name, "description": description, "parameters": {"type": "object"}}


# ── canonicalHeader ────────────────────────────────────────────────────────


def test_canonical_header_normalizes_empty_optional_fields_and_preserves_populated() -> None:
    """dsh parity: empty system / tools / adapterDefaults 字段 absent;populated 保留。"""
    assert canonicalHeader(
        EpochHeader(
            config=CONFIG,
            adapter_defaults={},
            system="",
            tools=(),
        )
    ) == EpochHeader(config=CONFIG)

    full = canonicalHeader(
        EpochHeader(
            config={**CONFIG, "max_tokens": 256_000},
            adapter_defaults={"max_tokens": True},
            system="s",
            tools=(tool("a"),),
        )
    )
    assert full == EpochHeader(
        config={**CONFIG, "max_tokens": 256_000},
        adapter_defaults={"max_tokens": True},
        system="s",
        tools=(tool("a"),),
    )


# ── headerEquals ──────────────────────────────────────────────────────────


def test_header_equals_compares_every_canonical_field_and_preserves_tool_order() -> None:
    """dsh parity: base = canonicalHeader({config, system, tools:[a]}) 比对各种变体。"""
    base = canonicalHeader(EpochHeader(config=CONFIG, system="s", tools=(tool("a"),)))

    # 结构等价: 重建同字段 EpochHeader(frozen+slots,等同 dsh structuredClone 语义)
    assert (
        headerEquals(
            base,
            EpochHeader(
                config=base.config,
                adapter_defaults=base.adapter_defaults,
                system=base.system,
                tools=base.tools,
            ),
        )
        is True
    )

    # 改 model → 不等
    assert headerEquals(base, replace_config(base, {"provider": "mock", "model": "other"})) is False

    # 加 reasoning_effort → 不等
    assert (
        headerEquals(
            base,
            replace_config(base, {**base.config, "reasoning_effort": "high"}),
        )
        is False
    )

    # 改 config + adapter_defaults → 不等
    assert (
        headerEquals(
            replace_config(base, {**base.config, "max_tokens": 256_000}),
            EpochHeader(
                config={**base.config, "max_tokens": 256_000},
                adapter_defaults={"max_tokens": True},
                system=base.system,
                tools=base.tools,
            ),
        )
        is False
    )

    # 改 system → 不等
    assert headerEquals(base, with_field(base, system="other")) is False

    # 改 tools 为空 → 不等(base 工具非空)
    assert headerEquals(base, with_field(base, tools=())) is False

    # 改 tools 元素 description → 不等
    assert headerEquals(base, with_field(base, tools=(tool("a", "changed"),))) is False

    # 调换 tools 顺序 → 不等
    assert (
        headerEquals(
            EpochHeader(config=CONFIG, tools=(tool("a"), tool("b"))),
            EpochHeader(config=CONFIG, tools=(tool("b"), tool("a"))),
        )
        is False
    )


def test_header_equals_treats_absent_and_empty_tool_arrays_as_equivalent() -> None:
    """dsh parity:tools absent 与 ``()`` 在 canonical 形态下等价(headerEquals 字段级)。"""
    # 归一后两者 tools 都是 () —— 等价
    assert (
        headerEquals(
            canonicalHeader(EpochHeader(config=CONFIG)),
            canonicalHeader(EpochHeader(config=CONFIG, tools=())),
        )
        is True
    )


# ── foldRequestHeader ──────────────────────────────────────────────────────


def test_fold_returns_supplied_baseline_when_no_snapshot_follows() -> None:
    """dsh parity:无关事件流,fold 返 ``None``;带 ``from_`` 续接时返 ``from_``。"""
    from_state: EpochHeader = EpochHeader(config=CONFIG, system="baseline")
    unrelated: list[dict[str, Any]] = [
        {"category": "turn/start", "payload": {"turn": 1}},
    ]

    assert foldRequestHeader(unrelated) is None
    assert foldRequestHeader(unrelated, from_=from_state) is from_state


def test_fold_takes_latest_full_snapshot_and_skips_unrelated_events() -> None:
    """dsh parity: fold 取最后一条 header;无关事件 skip。"""
    events: list[dict[str, Any]] = [
        {"category": "turn/start", "payload": {"turn": 1}},
        {
            "category": "spine.llm.request.header",
            "payload": {"config": CONFIG, "system": "first"},
        },
        {
            "category": "user/message",
            "payload": {
                "content": [{"type": "text", "text": "hi"}],
                "source": {"kind": "user"},
            },
        },
        {
            "category": "spine.llm.request.header",
            "payload": {"config": {"provider": "mock", "model": "other"}, "tools": []},
        },
    ]

    # 最后一条 header 配置 model="other",空 tools 被归一为 ()
    assert foldRequestHeader(events) == EpochHeader(config={"provider": "mock", "model": "other"})


# ── helpers ────────────────────────────────────────────────────────────────


def replace_config(header: EpochHeader, new_config: Mapping[str, Any]) -> EpochHeader:
    """测试 helper: 替换 config,其他字段保留。"""
    return EpochHeader(
        config=dict(new_config),
        adapter_defaults=header.adapter_defaults,
        system=header.system,
        tools=header.tools,
    )


def with_field(header: EpochHeader, **overrides: Any) -> EpochHeader:
    """测试 helper: 字段级覆盖。"""
    base = {
        "config": header.config,
        "adapter_defaults": header.adapter_defaults,
        "system": header.system,
        "tools": header.tools,
    }
    base.update(overrides)
    return EpochHeader(**base)
