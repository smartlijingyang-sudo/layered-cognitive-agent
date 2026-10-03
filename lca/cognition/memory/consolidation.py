"""ADR-0277 §2.3：remember 显式 consolidation 四决策。

encode（Craik & Lockhart 编码门控）→ link（Mem0 四操作的认知语义升级版对账）
→ decay（Ebbinghaus 式降权 + Jost 第二定律：一次只降一级，不删除）
→ schema（Letta sleep-time 提炼，离线跑，不在在线编排内）。

每次决策产出一条 ConsolidationRecord（C5 审计）：decision 四选一且 rationale
非空，非法 decision 在 ConsolidationOutcome 构造时运行时拦截（Literal 只做
静态检查）。所有"修改"都用 dataclasses.replace 产生新实例，旧对象保留
（Zep 非丢失式，C4 双时间线）。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal, Protocol

from .types import ConsolidationRecord, EpisodicTrace, SemanticClaim

try:  # P4 并行实现中；仅为类型导入，运行时走 duck-typing
    from .laya_backend import (  # type: ignore[import-not-found]
        LayaDecision,
        LayaScoreEngine,
    )
except ImportError:  # pragma: no cover - P4 落地前必然走这里
    LayaDecision = None  # type: ignore[assignment]
    LayaScoreEngine = None  # type: ignore[assignment]

__all__ = [
    "ConsolidationContext",
    "ConsolidationDecider",
    "ConsolidationOutcome",
    "DecayPolicy",
    "EncodeGate",
    "LayaDecider",
    "LinkDecider",
    "LinkResult",
    "RuleDecider",
    "RuleSchemaExtractor",
    "SchemaExtractor",
]

# C5：decision 四选一（运行时校验用，Literal 只做静态检查）
_DECISIONS: tuple[str, ...] = ("encode", "link", "decay", "schema")

# Jost 第二定律配套：salience 下限，只降权不删除
_SALIENCE_FLOOR = 0.05

# Laya choice 置信度低于此值时显式回退 RuleDecider（ADR 约定）
_LAYA_FALLBACK_CONFIDENCE = 0.6

# schema 提炼：同一 who 在 7 天窗口内出现 >=3 次相似 what
_SCHEMA_WINDOW_DAYS = 7.0
_SCHEMA_MIN_COUNT = 3
_SCHEMA_CONFIDENCE = 0.6

Effect = Literal["kept", "dropped", "superseded", "merged", "added", "decayed", "extracted"]


@dataclass(frozen=True)
class ConsolidationOutcome:
    """一次 consolidation 决策的结果。

    record 承载 C5 审计（decision 四选一、rationale 非空）；effect 描述该
    决策对记忆的实质影响。decision 非法时构造即抛 ValueError。
    """

    record: ConsolidationRecord
    effect: Effect

    def __post_init__(self) -> None:
        if self.record.decision not in _DECISIONS:
            raise ValueError(
                f"decision 必须为 {_DECISIONS} 四选一，实际={self.record.decision!r}"
            )


@dataclass(frozen=True)
class LinkResult:
    """reconcile 的完整产出：审计 outcome + 新旧 claim（C4 非丢失）。

    冲突时 retired_claim 为被填 valid_to 的旧 claim（不删除），new_claim 的
    supersedes 指向旧 claim id；merged/added 时 retired_claim 为 None。
    """

    outcome: ConsolidationOutcome
    new_claim: SemanticClaim
    retired_claim: SemanticClaim | None


@dataclass(frozen=True)
class ConsolidationContext:
    """decide() 的上下文：现有 claim + 世界时间。

    existing_claims 传入 list 会被规范化为 tuple（frozen 安全）；
    含已失效 claim（C4：历史只读，对账时由 LinkDecider 跳过）。
    """

    existing_claims: tuple[SemanticClaim, ...]
    now: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "existing_claims", tuple(self.existing_claims))


class ConsolidationDecider(Protocol):
    """consolidation 决策器协议：RuleDecider（确定性规则）与 LayaDecider（模型打分）可互换。"""

    def decide(
        self, candidate: EpisodicTrace, ctx: ConsolidationContext
    ) -> ConsolidationOutcome:
        """对候选 trace 做一次显式决策，返回带审计记录的结果。"""
        ...


# ---------------------------------------------------------------------------
# encode：Craik & Lockhart 编码门控
# ---------------------------------------------------------------------------


@dataclass
class EncodeGate:
    """编码门控：salience 低于阈值的候选在 encode 阶段被丢弃（ADR §4 A3）。"""

    salience_threshold: float = 0.3

    def __post_init__(self) -> None:
        if not 0.0 <= self.salience_threshold <= 1.0:
            raise ValueError(
                f"salience_threshold 必须在 0..1 之间，实际={self.salience_threshold!r}"
            )

    def evaluate(self, trace: EpisodicTrace) -> ConsolidationOutcome:
        """salience >= 阈值 → kept；低于阈值 → dropped（rationale 写明阈值与实际值）。"""
        if trace.salience >= self.salience_threshold:
            return ConsolidationOutcome(
                record=ConsolidationRecord(
                    decision="encode",
                    target_id=trace.id,
                    rationale=(
                        f"salience={trace.salience:.3f} >= 编码门控阈值 "
                        f"{self.salience_threshold:.3f}，允许编码"
                    ),
                ),
                effect="kept",
            )
        return ConsolidationOutcome(
            record=ConsolidationRecord(
                decision="encode",
                target_id=trace.id,
                rationale=(
                    f"salience={trace.salience:.3f} < 编码门控阈值 "
                    f"{self.salience_threshold:.3f}（Craik & Lockhart），"
                    "丢弃不编码（A3：阈值以下无写入）"
                ),
            ),
            effect="dropped",
        )


# ---------------------------------------------------------------------------
# link：Mem0 四操作的认知语义升级版对账
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _normalize(text: str) -> str:
    """归一化：小写、去标点、压缩空白。"""
    text = re.sub(r"[^\w\s]", "", text.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _topic_words(text: str) -> frozenset[str]:
    """主题词集合：长度>=2 的词；中文长串额外切二元组。

    v1 启发式：让"用户喜欢深色模式"这类无空格中文文本可比较。
    """
    words: set[str] = set()
    for token in _TOKEN_RE.findall(text):
        if len(token) < 2:
            continue
        words.add(token)
        if len(token) > 2 and _CJK_RE.search(token):
            words.update(token[i : i + 2] for i in range(len(token) - 1))
    return frozenset(words)


def _is_conflict(new_claim: str, old_claim: str) -> bool:
    """v1 冲突启发式：归一化文本不同 **且** 主题词有重叠。

    诚实标注：这是简单可解释的占位规则，不是真正的"内容矛盾"判定——
    主题词偶然重叠会导致误判，真正的语义矛盾需要 NLI/LLM（v2 插 Laya
    choice）。测试用固定用例钉住当前行为。
    """
    new, old = _normalize(new_claim), _normalize(old_claim)
    if not new or not old or new == old:
        return False
    return bool(_topic_words(new) & _topic_words(old))


def _supersede(
    new_claim: SemanticClaim, old_claim: SemanticClaim, now: datetime, by: str
) -> tuple[SemanticClaim, SemanticClaim, ConsolidationOutcome]:
    """冲突处理：旧 claim 填 valid_to 失效（不删除），新 claim supersedes 指向旧 id。"""
    retired = replace(old_claim, valid_to=now)
    updated_new = replace(
        new_claim,
        supersedes=old_claim.id,
        valid_from=new_claim.valid_from or now,
    )
    outcome = ConsolidationOutcome(
        record=ConsolidationRecord(
            decision="link",
            target_id=new_claim.id,
            rationale=(
                f"{by}：与现有 claim {old_claim.id} 冲突——旧 claim 填 "
                f"valid_to={now.isoformat()} 失效（不删除，C4），新 claim "
                f"supersedes 指向 {old_claim.id}"
            ),
        ),
        effect="superseded",
    )
    return updated_new, retired, outcome


class LinkDecider:
    """link 对账：新 claim 与现有 claim 逐条对账。

    冲突 → 旧 claim 填 valid_to（Zep 式失效不删除）+ supersedes 链；
    重复（归一化文本相同）→ merged；无关 → added。
    已失效（valid_to 非空）的旧 claim 跳过（C4：历史只读）。
    """

    def reconcile(
        self,
        new_claim: SemanticClaim,
        existing: list[SemanticClaim],
        now: datetime,
    ) -> LinkResult:
        """返回 LinkResult（含审计 outcome；冲突时同时带出新旧两个 claim）。"""
        for old in existing:
            if old.valid_to is not None:
                continue
            if _normalize(new_claim.claim) == _normalize(old.claim):
                outcome = ConsolidationOutcome(
                    record=ConsolidationRecord(
                        decision="link",
                        target_id=new_claim.id,
                        rationale=(
                            f"与现有 claim {old.id} 文本归一化后相同，"
                            f"合并到 {old.id}（不新增条目）"
                        ),
                    ),
                    effect="merged",
                )
                return LinkResult(outcome=outcome, new_claim=new_claim, retired_claim=None)
            if _is_conflict(new_claim.claim, old.claim):
                updated_new, retired, outcome = _supersede(
                    new_claim, old, now, by="规则判定冲突"
                )
                return LinkResult(
                    outcome=outcome, new_claim=updated_new, retired_claim=retired
                )
        outcome = ConsolidationOutcome(
            record=ConsolidationRecord(
                decision="link",
                target_id=new_claim.id,
                rationale=f"与 {len(existing)} 条现有 claim 均无冲突/重复，作为新条目添加",
            ),
            effect="added",
        )
        return LinkResult(outcome=outcome, new_claim=new_claim, retired_claim=None)


# ---------------------------------------------------------------------------
# decay：Ebbinghaus 式降权（Jost 第二定律：一次只降一级，不删除）
# ---------------------------------------------------------------------------


@dataclass
class DecayPolicy:
    """衰减策略：salience *= 0.5 ** (age_days / half_life)。

    只降权不删除；salience 下限 0.05（触底后 needs_decay 返回 False）。
    """

    half_life_days: float = 30.0

    def __post_init__(self) -> None:
        if self.half_life_days <= 0:
            raise ValueError(
                f"half_life_days 必须为正数，实际={self.half_life_days!r}"
            )

    def decayed_salience(self, trace: EpisodicTrace, now: datetime) -> float:
        """衰减后的 salience：下限 _SALIENCE_FLOOR，且永不高于原值（只降权）。"""
        age_days = max(0.0, (now - trace.when).total_seconds() / 86400.0)
        decayed = trace.salience * 0.5 ** (age_days / self.half_life_days)
        return min(max(decayed, _SALIENCE_FLOOR), trace.salience)

    def needs_decay(self, trace: EpisodicTrace, now: datetime, floor: float = 0.05) -> bool:
        """是否需要跑 decay 决策：高于下限且衰减后确实更低（还有降权空间）。"""
        return (
            trace.salience > floor
            and self.decayed_salience(trace, now) < trace.salience
        )


# ---------------------------------------------------------------------------
# 编排：RuleDecider（确定性）+ LayaDecider（模型打分，可插拔）
# ---------------------------------------------------------------------------


def _trace_to_claim(trace: EpisodicTrace, now: datetime) -> SemanticClaim:
    """v1 规则映射：trace.what 原文直转为 claim（confidence 取 salience）。"""
    return SemanticClaim(
        id=f"claim-{trace.id}",
        claim=trace.what,
        confidence=round(trace.salience, 3),
        sources=(trace.id,),
        valid_from=now,
        valid_to=None,
        supersedes=None,
    )


class RuleDecider(ConsolidationDecider):
    """确定性编排：encode → link → decay（schema 走离线，不在在线路径）。

    编排语义：encode 丢弃则短路；link 产出实质性变更（superseded/merged）
    则直接返回，保证审计记录不丢失；link 仅 added 时继续评估 decay；
    最终返回最后生效的决策。
    """

    def __init__(
        self,
        gate: EncodeGate | None = None,
        linker: LinkDecider | None = None,
        decay: DecayPolicy | None = None,
    ) -> None:
        self._gate = gate if gate is not None else EncodeGate()
        self._linker = linker if linker is not None else LinkDecider()
        self._decay = decay if decay is not None else DecayPolicy()

    def decide(
        self, candidate: EpisodicTrace, ctx: ConsolidationContext
    ) -> ConsolidationOutcome:
        outcome = self._gate.evaluate(candidate)
        if outcome.effect == "dropped":
            return outcome
        new_claim = _trace_to_claim(candidate, ctx.now)
        link_result = self._linker.reconcile(
            new_claim, list(ctx.existing_claims), ctx.now
        )
        if link_result.outcome.effect in ("superseded", "merged"):
            return link_result.outcome
        if self._decay.needs_decay(candidate, ctx.now):
            new_salience = self._decay.decayed_salience(candidate, ctx.now)
            age_days = (ctx.now - candidate.when).total_seconds() / 86400.0
            return ConsolidationOutcome(
                record=ConsolidationRecord(
                    decision="decay",
                    target_id=candidate.id,
                    rationale=(
                        f"trace 已存放 {age_days:.1f} 天（Jost 第二定律：一次只降一级）："
                        f"salience {candidate.salience:.3f} → {new_salience:.3f}，"
                        f"下限 {_SALIENCE_FLOOR}；只降权不删除"
                    ),
                ),
                effect="decayed",
            )
        return link_result.outcome


class LayaDecider(ConsolidationDecider):
    """Laya 模型打分版 decider：noul（值得提炼吗）+ choice（冲突三选一）。

    engine 接口（P4 的 lca/cognition/memory/laya_backend.py 提供，此处
    duck-typing，测试用 FakeEngine）：
      - is_available() -> bool
      - decide(state: dict, schema: dict) -> LayaDecision{decision, confidence, raw}

    fail-closed：engine 未注入或 is_available() 为 False 时 decide() 抛
    RuntimeError，绝不静默回退（静默回退会掩盖模型故障）。
    choice confidence < 0.6 时显式回退 RuleDecider（ADR 约定）。
    decay 仍由 RuleDecider 编排负责，Laya 只接管 encode 门控与 link 对账的
    智能部分。
    """

    def __init__(
        self,
        engine: Any = None,
        fallback: ConsolidationDecider | None = None,
    ) -> None:
        self._engine = engine
        self._fallback = fallback if fallback is not None else RuleDecider()

    def decide(
        self, candidate: EpisodicTrace, ctx: ConsolidationContext
    ) -> ConsolidationOutcome:
        engine = self._engine
        if engine is None:
            raise RuntimeError(
                "LayaDecider 未注入 engine：fail-closed，拒绝做 consolidation 决策"
            )
        if not engine.is_available():
            raise RuntimeError(
                "LayaScoreEngine.is_available()=False：fail-closed，拒绝做 consolidation 决策"
            )
        now = ctx.now
        # noul：值得提炼/编码吗
        noul = engine.decide(
            {"what": candidate.what, "salience": candidate.salience},
            {"worth_extracting": "bool"},
        )
        raw = noul.raw if isinstance(noul.raw, dict) else {}
        if not raw.get("worth_extracting", False):
            return ConsolidationOutcome(
                record=ConsolidationRecord(
                    decision="encode",
                    target_id=candidate.id,
                    rationale=(
                        "Laya noul 判定不值得编码（worth_extracting=False，"
                        f"confidence={noul.confidence:.2f}）：丢弃"
                    ),
                ),
                effect="dropped",
            )
        # choice：与每条有效旧 claim 做三选一
        new_claim = _trace_to_claim(candidate, now)
        valid_olds = [o for o in ctx.existing_claims if o.valid_to is None]
        for old in valid_olds:
            res = engine.decide(
                {"new_claim": new_claim.claim, "old_claim": old.claim},
                {"resolution": "enum[supersede,merge,keep_both]"},
            )
            if res.confidence < _LAYA_FALLBACK_CONFIDENCE:
                return self._fallback.decide(candidate, ctx)
            rraw = res.raw if isinstance(res.raw, dict) else {}
            resolution = rraw.get("resolution", "keep_both")
            tag = f"Laya choice 判定 resolution={resolution}（confidence={res.confidence:.2f}）"
            if resolution == "supersede":
                _, _, outcome = _supersede(new_claim, old, now, by=tag)
                return outcome
            if resolution == "merge":
                return ConsolidationOutcome(
                    record=ConsolidationRecord(
                        decision="link",
                        target_id=new_claim.id,
                        rationale=f"{tag}：与现有 claim {old.id} 合并（不新增条目）",
                    ),
                    effect="merged",
                )
            # keep_both → 继续看下一条
        return ConsolidationOutcome(
            record=ConsolidationRecord(
                decision="link",
                target_id=new_claim.id,
                rationale=(
                    f"Laya choice 对 {len(valid_olds)} 条有效 claim 全票 keep_both："
                    "作为新条目添加"
                ),
            ),
            effect="added",
        )


# ---------------------------------------------------------------------------
# schema：Letta sleep-time 提炼（离线跑）
# ---------------------------------------------------------------------------


class SchemaExtractor(Protocol):
    """sleep-time 提炼协议：离线 pass，从 episodic 提炼 semantic。"""

    def extract(
        self, traces: list[EpisodicTrace], now: datetime
    ) -> list[tuple[SemanticClaim, ConsolidationOutcome]]:
        """返回 (提炼出的 claim, 审计 outcome) 列表。"""
        ...


def _schema_claim_id(who_key: tuple[str, ...], norm_what: str) -> str:
    """确定性 claim id：同一 (who, 主题) 重复提炼时 id 稳定。"""
    digest = hashlib.md5(
        f"{'|'.join(who_key)}\x00{norm_what}".encode()
    ).hexdigest()[:12]
    return f"schema-{digest}"


class RuleSchemaExtractor(SchemaExtractor):
    """v1 规则版 schema 提炼（Letta sleep-time consolidation 的占位实现）。

    规则：同一 who 在 7 天窗口内出现 >=3 次相似 what（归一化文本相同）
    → 提炼一条 SemanticClaim（confidence=0.6，sources=窗口内 trace ids）。
    诚实标注：这是可解释的占位规则，真正的"模式发现"需要语义聚类，
    LLM 版以后插。
    """

    def extract(
        self, traces: list[EpisodicTrace], now: datetime
    ) -> list[tuple[SemanticClaim, ConsolidationOutcome]]:
        groups: dict[tuple[tuple[str, ...], str], list[EpisodicTrace]] = {}
        for t in traces:
            key = (tuple(sorted(set(t.who))), _normalize(t.what))
            groups.setdefault(key, []).append(t)
        results: list[tuple[SemanticClaim, ConsolidationOutcome]] = []
        for (who_key, norm_what), members in groups.items():
            members.sort(key=lambda t: t.when)
            window = self._dense_window(members)
            if window is None:
                continue
            claim = SemanticClaim(
                id=_schema_claim_id(who_key, norm_what),
                claim=window[0].what,
                confidence=_SCHEMA_CONFIDENCE,
                sources=tuple(t.id for t in window),
                valid_from=now,
                valid_to=None,
                supersedes=None,
            )
            who_label = "、".join(who_key) if who_key else "（who 未标注）"
            outcome = ConsolidationOutcome(
                record=ConsolidationRecord(
                    decision="schema",
                    target_id=claim.id,
                    rationale=(
                        f"同一 who（{who_label}）在 7 天窗口内出现 {len(window)} 次"
                        "相似主题（归一化文本相同），提炼为语义断言"
                        "（Letta sleep-time 规则版占位，LLM 版待插）"
                    ),
                ),
                effect="extracted",
            )
            results.append((claim, outcome))
        return results

    @staticmethod
    def _dense_window(
        members: list[EpisodicTrace],
    ) -> list[EpisodicTrace] | None:
        """滑动窗口：在 members（已按 when 排序）中找 7 天内 >=3 条的首个窗口。"""
        n = len(members)
        for i in range(n):
            j = i
            while (
                j < n
                and (members[j].when - members[i].when).total_seconds() / 86400.0
                <= _SCHEMA_WINDOW_DAYS
            ):
                j += 1
            if j - i >= _SCHEMA_MIN_COUNT:
                return members[i:j]
        return None
