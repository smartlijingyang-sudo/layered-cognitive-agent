# -*- coding: utf-8 -*-
"""WorthinessGate：主动消息裁决门（纯函数，可测）。

调用方声明 + gate 交叉校验（ADR-0264 §4①，不做独立评估步）：

- 调用方在 ``ProactiveRequest.declared`` 中声明期望的裁决；
  gate 只做 **downgrade-only** 交叉校验：只能把裁决往"更不打扰"
  方向移动（DELIVER_CHAT→DELIVER_QUIET→SILENT），绝不能往更打扰
  方向升级。修的是"申请人=批准人"的自授权——校验是机械的，
  不多花一次模型调用。
- ``requested=True`` 必须携带可验证的 ``request_ref``：
  gate 校验该引用存在于 trigger 上下文背书的
  ``known_request_refs`` 集合中，否则按 unrequested 处理。

决策矩阵（gate 自有判断，按序，首个命中即返回）：

1. 凭证红线：content 命中凭证模式 → REJECTED（最高抑制，无视
   declared 与 policy；对齐 ADR-0260 §5④：脱敏写入制造"记下了
   完整事实"的幻觉，比不记更危险）。
2. 用户明确要求/触发（requested=True 且 request_ref 已验证）→
   DELIVER_CHAT，回发起上下文。
3. 未被要求：
   a. 例行（is_routine）或无实质新信息（not is_novel）→ SILENT
      （合法默认项）；
   b. 值得打断（worth_interrupting）→ DELIVER_CHAT；
   c. 内容依赖记忆但无记忆源 → DELIVER_QUIET + 标注"未经检索"
     （对齐 ADR-0260 C2：不许在无记忆源时假装记得）；
   d. 其余 → DELIVER_QUIET（安静面）。

政策层（ProactivePolicy，gate 为唯一卡点）：
- ``enabled=False`` → SILENT（REJECTED 除外：凭证红线是安全抑制，
  不受开关影响——反正不投递，且调用方照记 warning）；
- quiet hours 内裁决上限为 DELIVER_QUIET（消息照投递，只是不打断）。

muse 思想注记：fail-closed 只用在可精确判定的地方——
凭证模式命中与 request_ref 集合成员是精确可判定的，所以 fail-closed；
"值得打断"不可机械判定，所以默认走安静面而非聊天
（fail-open + 显式分流，不误杀也不打扰）。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from lca.contracts.models.proactive.policy import ProactivePolicy
from lca.contracts.models.proactive.worthiness import (
    ProactiveRequest,
    VerdictKind,
    WorthinessVerdict,
)

_log = logging.getLogger(__name__)

# 凭证模式：精确可判定的红线。命中即整条拒绝，不做脱敏改写。
_CREDENTIAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|pwd)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(bearer\s+[A-Za-z0-9\-._~+/]+=*)"),
    re.compile(r"\b(sk-[A-Za-z0-9]{8,})"),
    re.compile(r"(?i)\b(mnemonic|private[_-]?key)\b\s*[:=]"),
)

# 打扰度：数值越小越不打扰。downgrade-only 即取打扰度更低者。
_INTRUSIVENESS: dict[VerdictKind, int] = {
    VerdictKind.SILENT: 0,
    VerdictKind.DELIVER_QUIET: 1,
    VerdictKind.DELIVER_CHAT: 2,
}


def _contains_credential(content: str) -> bool:
    return any(p.search(content) is not None for p in _CREDENTIAL_PATTERNS)


def _verify_requested(request: ProactiveRequest) -> bool:
    """requested 的机械校验：True 必须携带非空 request_ref，且该引用在
    trigger 上下文背书的 known_request_refs 集合中。纯集合成员检查，
    精确可判定 → fail-closed（校验不过按 unrequested 处理）。"""
    if not request.requested:
        return False
    ref = (request.request_ref or "").strip()
    return bool(ref) and ref in set(request.known_request_refs)


def _decide_matrix(
    request: ProactiveRequest, effective_requested: bool
) -> WorthinessVerdict:
    """gate 自有决策矩阵（不含调用方声明的影响）。"""
    # 用户明确要求/触发（已验证）→ 必达
    if effective_requested:
        return WorthinessVerdict(
            kind=VerdictKind.DELIVER_CHAT,
            reason=(
                "用户明确触发（request_ref="
                f"{request.request_ref} 已验证），必达并回发起上下文"
            ),
        )

    # 例行或无新信息 → 静默（合法默认项）
    if request.is_routine or not request.is_novel:
        return WorthinessVerdict(
            kind=VerdictKind.SILENT,
            reason="例行事项或无实质新信息，静默",
        )

    # 值得打断 → 推聊天
    if request.worth_interrupting:
        return WorthinessVerdict(
            kind=VerdictKind.DELIVER_CHAT,
            reason="实质新信息且值得打断",
        )

    # 依赖记忆但无记忆源 → 降级安静面 + 标注
    if request.message.requires_memory and not request.has_memory_source:
        return WorthinessVerdict(
            kind=VerdictKind.DELIVER_QUIET,
            reason="内容依赖记忆但无记忆源，降级安静面",
            annotate_unretrieved=True,
        )

    # 其余 → 安静面
    return WorthinessVerdict(
        kind=VerdictKind.DELIVER_QUIET,
        reason="未达打断阈值，走安静面",
    )


def _apply_downgrade_only(
    request: ProactiveRequest, base: WorthinessVerdict
) -> WorthinessVerdict:
    """downgrade-only 合并：取调用方声明与 gate 自有判断中打扰度更低者。

    - base 更不打扰 → 真降级（审计理由写明）；
    - base 更打扰 → 不升级，维持调用方声明。
    """
    base_level = _INTRUSIVENESS[base.kind]
    declared_level = _INTRUSIVENESS[request.declared]
    if base_level <= declared_level:
        if base.kind == request.declared:
            return base
        return WorthinessVerdict(
            kind=base.kind,
            reason=(
                f"调用方声明 {request.declared.value}，gate 证据不足"
                f"降级为 {base.kind.value}：{base.reason}"
            ),
            annotate_unretrieved=base.annotate_unretrieved,
        )
    return WorthinessVerdict(
        kind=request.declared,
        reason=(
            f"调用方声明 {request.declared.value}，gate 按 downgrade-only "
            f"不升级（gate 自有判断 {base.kind.value} 更打扰，不予采纳）"
        ),
        annotate_unretrieved=False,
    )


def _in_quiet_hours(policy: ProactivePolicy, now: datetime | None) -> bool:
    """是否落在 quiet hours 内（处理跨午夜；起止相同视为未设置）。"""
    try:
        tz = ZoneInfo(policy.timezone)
    except Exception:  # noqa: BLE001 — 时区配错不炸 tick，降级为不限流并记 warning
        _log.warning("proactive.bad_timezone timezone=%r", policy.timezone)
        return False
    if now is None:
        current = datetime.now(tz)
    elif now.tzinfo is None:
        current = now.replace(tzinfo=tz)
    else:
        current = now.astimezone(tz)
    t = current.time()
    start, end = policy.quiet_hours_start, policy.quiet_hours_end
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end  # 跨午夜


def _apply_policy(
    verdict: WorthinessVerdict, policy: ProactivePolicy, now: datetime | None
) -> WorthinessVerdict:
    """政策层：gate 内唯一卡点。"""
    # REJECTED 是安全抑制，不受政策开关影响（反正不投递；调用方照记 warning）。
    if verdict.kind == VerdictKind.REJECTED:
        return verdict
    if not policy.enabled:
        return WorthinessVerdict(
            kind=VerdictKind.SILENT,
            reason="全局主动消息开关已关闭（ProactivePolicy.enabled=False），静默",
        )
    if verdict.kind == VerdictKind.DELIVER_CHAT and _in_quiet_hours(policy, now):
        return verdict.model_copy(
            update={
                "kind": VerdictKind.DELIVER_QUIET,
                "reason": verdict.reason
                + "（quiet hours 内上限为安静面：消息照投递，只是不打断）",
            }
        )
    return verdict


def decide(
    request: ProactiveRequest,
    *,
    policy: ProactivePolicy | None = None,
    now: datetime | None = None,
) -> WorthinessVerdict:
    """对一次主动消息请求做纯函数裁决。

    - ``policy`` 为 None 时只走矩阵 + downgrade-only（保持旧调用兼容）；
    - 传入 ``policy`` 时再过政策层（总开关 / quiet hours）。
    """
    content = request.message.content

    # 0. 凭证红线（最高抑制：无视 declared 与 policy）
    if _contains_credential(content):
        return WorthinessVerdict(
            kind=VerdictKind.REJECTED,
            reason="内容命中凭证模式，整条拒绝（ADR-0260 §5④）",
        )

    # 1. requested 机械校验
    effective_requested = _verify_requested(request)

    # 2. gate 自有矩阵
    base = _decide_matrix(request, effective_requested)

    # 3. downgrade-only 合并
    verdict = _apply_downgrade_only(request, base)

    # 3b. 审计注记：声称 requested 但 request_ref 未通过验证
    if request.requested and not effective_requested:
        verdict = verdict.model_copy(
            update={
                "reason": verdict.reason
                + "（requested 声明的 request_ref 缺失或无法验证，已按未要求处理）",
            }
        )

    # 4. 政策层（gate 为唯一卡点）
    if policy is not None:
        verdict = _apply_policy(verdict, policy, now)
    return verdict


__all__ = ["decide"]
