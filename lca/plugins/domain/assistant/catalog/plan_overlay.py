"""plan-overlay YAML 解析与 schema 校验（ADR-0242 I-B11）。

``{home}/plan.yaml`` 的读取 / ``revise_profile`` 文本校验 / YAML→``PlanOverlay``
解析统一走 ``_parse_plan_overlay``；形状非法 fail-closed，防止损坏覆盖
静默进入 Resolve → Compile 管线。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lca.contracts.models.assistant.plan_overlay import PlanOverlay
from lca.plugins.assistant.home._home_layout import AssistantCatalogError


class PlanOverlayValidationError(AssistantCatalogError):
    """``{home}/plan.yaml`` schema 校验失败（fail-closed，ADR-0242 I-B11）。

    消息必须指出文件路径与底层校验错误，便于用户经 ``revise_profile``
    修正后重试；不允许静默忽略损坏的覆盖。
    """


def _load_plan_overlay(home: Path) -> PlanOverlay | None:
    """读 ``{home}/plan.yaml`` 并校验为 ``PlanOverlay``；文件缺失返回 None。

    旧助理（创建于 plan.yaml 进 digest 之前）无该文件 ⇒ 返回 None（无覆盖，
    I-B8 无 overlay 路径行为不变）。文件存在但 schema 非法 ⇒ fail-closed，
    防止损坏的覆盖静默进入 Resolve → Compile 管线。
    """
    plan_path = home / "plan.yaml"
    if not plan_path.is_file():
        return None
    return _parse_plan_overlay(plan_path.read_text(encoding="utf-8"), source=str(plan_path))


def _validate_plan_yaml_text(text: str) -> PlanOverlay:
    """校验 ``revise_profile`` 传入的 plan.yaml 原始文本（ADR-0242 D10）。"""
    return _parse_plan_overlay(text, source="plan.yaml")


def _parse_plan_overlay(text: str, *, source: str) -> PlanOverlay:
    """YAML 文本 → ``PlanOverlay``；形状非法抛 ``PlanOverlayValidationError``。

    只做 schema 形状校验（未知字段 fail-closed）；模板 / section / bundle
    的「已登记」校验在 compile 层（持有注册表的层）。
    """
    try:
        raw = yaml.safe_load(text) or {}
        if not isinstance(raw, dict):
            raise PlanOverlayValidationError(
                f"{source}: 顶层必须是 mapping，得到 {type(raw).__name__}"
            )
        return PlanOverlay.model_validate(raw)
    except PlanOverlayValidationError:
        raise
    except Exception as exc:
        raise PlanOverlayValidationError(f"{source}: plan.yaml 校验失败: {exc}") from exc
