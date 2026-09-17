"""Pin the aggregate semantics of the ``failure_kind`` closed set.

一个 turn fork 出 N 个调用时,聚合 Observation / EffectReceipt 只能带一个
``failure_kind``。折叠规则由词表自己拥有(``lca/contracts/atoms/semantic/
keys.py``),因为 ``None`` 在那条边界上是承载语义的:它表示 host 没能把 effect
派出去、没有任何工具报告过结果,``act.observe.terminate_decide`` 据此收口 run
(ADR-0230 Amendment)。折叠只要丢掉一个分量的分类,就会把「批里有工具失败」
误报成「无工具报告」。
"""

from __future__ import annotations

from itertools import permutations

import pytest

from lca.contracts.atoms.semantic.keys import (
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_PRECEDENCE,
    FAILURE_KIND_TOOL_WIRE,
    FAILURE_KIND_TRANSIENT,
    FAILURE_KIND_VALIDATION,
    fold_failure_kinds,
)


def test_no_classification_folds_to_none() -> None:
    assert fold_failure_kinds([]) is None
    assert fold_failure_kinds([None, "", None]) is None


def test_single_classification_passes_through() -> None:
    for kind in FAILURE_KIND_PRECEDENCE:
        assert fold_failure_kinds([None, kind]) == kind


def test_precedence_runs_from_the_model_outward_to_infrastructure() -> None:
    assert FAILURE_KIND_PRECEDENCE == (
        FAILURE_KIND_TOOL_WIRE,
        FAILURE_KIND_VALIDATION,
        FAILURE_KIND_EXECUTION,
        FAILURE_KIND_TRANSIENT,
    )
    assert fold_failure_kinds([FAILURE_KIND_TRANSIENT, FAILURE_KIND_EXECUTION]) == (
        FAILURE_KIND_EXECUTION
    )
    assert fold_failure_kinds([FAILURE_KIND_EXECUTION, FAILURE_KIND_VALIDATION]) == (
        FAILURE_KIND_VALIDATION
    )


@pytest.mark.parametrize("order", list(permutations(FAILURE_KIND_PRECEDENCE)))
def test_fold_is_order_independent(order: tuple[str, ...]) -> None:
    """并发调度与模型 emit 顺序都不得改变聚合分类(C8)。"""

    assert fold_failure_kinds(order) == FAILURE_KIND_TOOL_WIRE


def test_non_string_bag_values_are_not_classifications() -> None:
    """``Observation.extra`` 是 ``dict[str, Any]``;折叠自己挡住非字符串取值。"""

    assert fold_failure_kinds([123, object(), None, FAILURE_KIND_TRANSIENT]) == (
        FAILURE_KIND_TRANSIENT
    )


def test_unknown_tag_still_counts_as_classified() -> None:
    """扩充词表不会把一个批次悄悄降级成 host 派发失败。"""

    assert fold_failure_kinds([FAILURE_KIND_EXECUTION, "quota"]) == FAILURE_KIND_EXECUTION
    assert fold_failure_kinds(["quota"]) == "quota"


def test_unknown_tags_fold_deterministically() -> None:
    assert fold_failure_kinds(["zeta", "alpha"]) == "alpha"
    assert fold_failure_kinds(["alpha", "zeta"]) == "alpha"
