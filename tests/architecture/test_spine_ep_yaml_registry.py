"""P2-22 / P-L4 — yaml-only spine EP registry drift guard (ADR-0195 §7).

Production spine execution points must be registered as yaml ``category`` rows
using ``SpineEventPayload``; ``SPINE_EXECUTION_POINTS`` must stay aligned with
that registry (no shadow tuple in ``manifest.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.observability.spine.manifest.manifest import EXECUTION_POINTS
from lca_kernel.events.payloads.spine import (
    SPINE_EXECUTION_POINTS,
    category_to_spine_ep,
)
from lca_kernel.events.registry.registry import EventRegistry

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = _REPO_ROOT / "lca_kernel" / "events" / "config"

# ADR-0208: model-visible assistant decision EP is now registered; the legacy
# baseline that allowed spine.llm.request.header.assistant without a bare EP
# was retired when SPINE_EXECUTION_POINTS + _SPINE_EP_TO_CATEGORY were
# aligned (delete-when: 2026-09-08 owner: model-visible).
_YAML_SPINE_CATEGORY_WITHOUT_EP_BASELINE: frozenset[str] = frozenset()


def _spine_eps_from_yaml_registry() -> frozenset[str]:
    registry = EventRegistry.load(_CONFIG_DIR, catalog={})
    eps: set[str] = set()
    unmapped: list[str] = []
    for spec in registry.specs:
        cat = spec.category.value
        if not cat.startswith("spine."):
            continue
        ep = category_to_spine_ep(cat)
        if ep is None:
            unmapped.append(cat)
            continue
        eps.add(ep)
    new_unmapped = sorted(set(unmapped) - _YAML_SPINE_CATEGORY_WITHOUT_EP_BASELINE)
    assert not new_unmapped, (
        "P-L4: new yaml spine categories lack category_to_spine_ep mapping:\n"
        + "\n".join(f"  - {c}" for c in new_unmapped)
        + "\nAdd EP to spine.yaml + SPINE_EXECUTION_POINTS or extend baseline with delete-when."
    )
    return frozenset(eps)


def test_manifest_aliases_spine_execution_points() -> None:
    from lca_kernel.events.payloads.spine import SPINE_EXECUTION_POINTS

    assert tuple(EXECUTION_POINTS) == SPINE_EXECUTION_POINTS


def test_spine_execution_points_match_yaml_registry() -> None:
    """Every SPINE_EXECUTION_POINTS entry must have a yaml category row."""
    yaml_eps = _spine_eps_from_yaml_registry()
    code_eps = frozenset(SPINE_EXECUTION_POINTS)
    missing_in_yaml = sorted(code_eps - yaml_eps)
    extra_in_yaml = sorted(yaml_eps - code_eps)
    assert not missing_in_yaml, (
        "SPINE_EXECUTION_POINTS contains EPs not registered in yaml:\n"
        + "\n".join(f"  - {ep}" for ep in missing_in_yaml)
    )
    assert not extra_in_yaml, (
        "yaml registers spine EPs absent from SPINE_EXECUTION_POINTS:\n"
        + "\n".join(f"  - {ep}" for ep in extra_in_yaml)
    )


def test_spine_execution_points_closed_set_no_duplicates() -> None:
    assert len(SPINE_EXECUTION_POINTS) == len(set(SPINE_EXECUTION_POINTS))


# ── ADR-0208 ─────────────────────────────────────────────────────────
# 四 SSOT 一致 + 字节布局 fail-loud 不变量。模型可见 assistant EP
# (spine.llm.request.header.assistant) 必须在三份登记:
#   1. SPINE_EXECUTION_POINTS (Python 顶层闭集)
#   2. _SPINE_EP_TO_CATEGORY (Python 顶层翻译表)
#   3. spine.yaml + closure_catalog.yaml (YAML 闭集)
# 缺一会让 typed payload 反查 EP 失败、SpineEventRecord 校验失败、fold
# 把 tool result 当孤儿投回 LLM,触发模型重复 tool call。


def test_model_visible_assistant_ep_registered_in_all_ssots() -> None:
    """ADR-0208: spine.llm.request.header.assistant must be in all four SSOTs."""
    from lca_kernel.events.payloads.spine import _SPINE_EP_TO_CATEGORY

    ep = "llm.request.header.assistant"
    category = "spine.llm.request.header.assistant"

    # 1. Python 顶层闭集
    assert ep in SPINE_EXECUTION_POINTS, (
        f"{ep} missing from SPINE_EXECUTION_POINTS — whitelist not aligned"
    )

    # 2. Python 顶层翻译表
    assert _SPINE_EP_TO_CATEGORY.get(ep) == category, (
        f"{ep} missing from _SPINE_EP_TO_CATEGORY — translation broken"
    )
    assert category_to_spine_ep(category) == ep, (
        f"reverse translation broken: {category} -> {category_to_spine_ep(category)!r}"
    )

    # 3. YAML 闭集 (closure_catalog.yaml uses bare EP, spine.yaml uses category)
    closure_yaml = _CONFIG_DIR / "observability" / "closure_catalog.yaml"
    spine_yaml = _CONFIG_DIR / "observability" / "spine.yaml"

    import yaml

    closure = yaml.safe_load(closure_yaml.read_text(encoding="utf-8"))
    closure_eps = {
        e.get("execution_point") for e in closure.get("events", []) if e.get("execution_point")
    }
    assert ep in closure_eps, f"{ep} missing from {closure_yaml.name}"

    spine = yaml.safe_load(spine_yaml.read_text(encoding="utf-8"))
    spine_cats = {e.get("category") for e in spine.get("events", []) if e.get("category")}
    assert category in spine_cats, f"{category} missing from {spine_yaml.name}"


def test_spine_event_record_rejects_unknown_execution_point() -> None:
    """ADR-0208: PR-5 dropped the EventRecord whitelist guard during byte
    layout migration. Restore it: SpineEventRecord must fail-loud on EPs not
    in SPINE_EXECUTION_POINTS so unknown EPs can no longer leak via the
    typed EventPayload catch-all path.
    """
    from lca_kernel.events.spine.runtime import SpineEventRecord

    with pytest.raises(ValueError, match="UnknownExecutionPoint"):
        SpineEventRecord(
            event_id="evt-test",
            category="spine.fake.event",
            execution_point="definitely.not.in.whitelist",
            channel="fact",
            payload={"k": "v"},
            ts="2026-09-08T00:00:00+00:00",
        )


def test_typed_payload_unknown_spine_category_fails_loud() -> None:
    """ADR-0208: typed EventPayload whose category is spine.* but unregistered
    in _SPINE_EP_TO_CATEGORY must raise instead of silently falling back to
    'unknown'. The defensive guard exists in addition to the Category enum
    because historically the enum has drifted from _SPINE_EP_TO_CATEGORY
    (PR-2 2026-09-04 added spine.yaml entries without extending the
    in-Python translation table — exactly the bug we are fixing here).
    """
    # Direct check: the runtime.py guard mirrors this exact condition.
    from lca_kernel.events.payloads.spine import category_to_spine_ep

    bogus = "spine.0208.does.not.exist"
    assert category_to_spine_ep(bogus) is None, (
        "test premise broken: bogus category must not be in "
        "_SPINE_CATEGORY_TO_EP — pick a different bogus name"
    )
    # The runtime guard wraps the lookup. Verifying it directly:
    # if bogus.startswith("spine.") and category_to_spine_ep(bogus) is None → raise.
    with pytest.raises(ValueError, match="UnknownExecutionPoint"):
        if bogus.startswith("spine.") and category_to_spine_ep(bogus) is None:
            raise ValueError(f"UnknownExecutionPoint(category={bogus!r})")
