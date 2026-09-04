"""Assistant domain EP closure —— ADR-0187 §3 D8 闭集扩展的 contracts 层登记。

助理域新增 12 个 EP（``assistant.created`` / ``assistant.bootstrap.completed``
等），构成本仓 Spine 事件词表的闭集扩展。每条必含 ``assistant_id`` /
``revision_seq`` / ``manifest_digest`` / ``actor`` 四个字段；下游
``assistant.*`` 插件（PR-3+）按本闭集发射。

本模块是 contracts 层 EP 描述符的单一登记源：

- EP 词表本身 = frozen tuple ``ASSISTANT_EVENT_POINTS``（不增不减，CI 守护）；
- 对应 cordis 派生名 = ``cordis_event_table.ASSISTANT_CORDIS_NAMES`` 字典；
- 真实 ``EventDescriptor`` 元数据 = ``ASSISTANT_EVENT_DESCRIPTORS``，由
  PR-3 的 ``event_descriptors_data.build_default_registry()`` 在 boot 期
  一次性导入 ``InMemoryEventDescriptorRegistry``。

**无 ADR 不增不删**（AGENTS.md §3 C1 闭集）。
"""

from __future__ import annotations

from typing import Final

from lca.contracts.models.observability.event import (
    EventAudience,
    EventDescriptor,
    EventDurability,
    EventPlane,
    EventSensitivity,
)

# ── EP 词表（12 项闭集） ────────────────────────────────────

ASSISTANT_CREATED: Final[str] = "assistant.created"
ASSISTANT_BOOTSTRAP_COMPLETED: Final[str] = "assistant.bootstrap.completed"
ASSISTANT_PROFILE_REVISED: Final[str] = "assistant.profile.revised"
ASSISTANT_PAUSED: Final[str] = "assistant.paused"
ASSISTANT_RESUMED: Final[str] = "assistant.resumed"
ASSISTANT_SKILL_INSTALLED: Final[str] = "assistant.skill.installed"
ASSISTANT_SKILL_ACTIVATED: Final[str] = "assistant.skill.activated"
ASSISTANT_SKILL_EVOLVED_PROPOSED: Final[str] = "assistant.skill.evolved.proposed"
ASSISTANT_SKILL_EVOLVED_PROMOTED: Final[str] = "assistant.skill.evolved.promoted"
ASSISTANT_JOB_REGISTERED: Final[str] = "assistant.job.registered"
ASSISTANT_JOB_FIRED: Final[str] = "assistant.job.fired"
ASSISTANT_RETIRED: Final[str] = "assistant.retired"

# 闭集快照（CI 守护：长度恒等于 12；增减必先 ADR）
ASSISTANT_EVENT_POINTS: Final[tuple[str, ...]] = (
    ASSISTANT_CREATED,
    ASSISTANT_BOOTSTRAP_COMPLETED,
    ASSISTANT_PROFILE_REVISED,
    ASSISTANT_PAUSED,
    ASSISTANT_RESUMED,
    ASSISTANT_SKILL_INSTALLED,
    ASSISTANT_SKILL_ACTIVATED,
    ASSISTANT_SKILL_EVOLVED_PROPOSED,
    ASSISTANT_SKILL_EVOLVED_PROMOTED,
    ASSISTANT_JOB_REGISTERED,
    ASSISTANT_JOB_FIRED,
    ASSISTANT_RETIRED,
)

# 闭集必备字段（每条 EP 必含 assistant_id / revision_seq / manifest_digest / actor）
ASSISTANT_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "assistant_id",
    "revision_seq",
    "manifest_digest",
    "actor",
)


# ── cordis 派生名（与 cordis_event_table 字面同步） ────────────
#
# 命名规则：cordis_name 一律以 ``"agent."`` 前缀收口（ADR-0169 L12），
# 助理域 EP 一律映射为 ``"agent.assistant.*"`` 子树。
#
# 不在此处依赖 ``cordis_event_table`` 模块以避免 import 环；字面字典与
# ``cordis_event_table._CORDIS_EVENT_TABLE_ENTRIES`` 末尾 12 条一一对应，
# 由 ``tests/contracts/observability/test_assistant_ep_closure.py`` 闭环守住。

ASSISTANT_CORDIS_NAMES: Final[dict[str, str]] = {ep: f"agent.{ep}" for ep in ASSISTANT_EVENT_POINTS}


# ── EventDescriptor 元数据（PR-3 注入 ``InMemoryEventDescriptorRegistry``）──
#
# 本元数据与 ``infrastructure/observability/events/event_descriptors_data.py``
# 的 ``build_default_registry()`` 同源；此处先在 contracts 层冻结，避免 PR-3
# 重复填写。emitter 全部走 ``"lca.plugins.assistant.*"`` 命名空间，PR-3 插件
# 上线后由架构测试守住（emitter 与 module id 字面前缀一致）。

_ASSISTANT_EMITTER_NAMESPACE: Final[str] = "lca.plugins.assistant"
_ASSISTANT_EVENT_DESCRIPTORS: Final[tuple[EventDescriptor, ...]] = (
    EventDescriptor(
        type_name=ASSISTANT_CREATED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.catalog",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="工厂创建成功（ADR-0187 §3 D8）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_BOOTSTRAP_COMPLETED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.bootstrap",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="BOOTSTRAP.md 完成并删除（ADR-0187 §3 D8）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_PROFILE_REVISED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.catalog",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="配置面变更（带 revision_seq++）（ADR-0187 §3 D8）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_PAUSED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.catalog",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="status 切换 paused；paused 助理拒收新 run（ADR-0187 §3 D8）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_RESUMED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.catalog",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="status 切换 resumed（ADR-0187 §3 D8）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_SKILL_INSTALLED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.skill_overlay",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="外部 URL/市场安装（已验证后）（ADR-0187 §3 D8 + §3 D9）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_SKILL_ACTIVATED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.skill_overlay",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="本 run activate（ADR-0187 §3 D8）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_SKILL_EVOLVED_PROPOSED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.evolve",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="evolve 提案进入 experiment（默认不落盘）（ADR-0187 §3 D8 + D9）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_SKILL_EVOLVED_PROMOTED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.evolve",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="0067 提升进 Home（ADR-0187 §3 D8 + D9）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_JOB_REGISTERED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.jobs",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="JobSpec 注册进 0093 WorkQueue（ADR-0187 §3 D8 + D10）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_JOB_FIRED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.jobs",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="Trigger 投递一次（scheduled.fire）（ADR-0187 §3 D8 + D10）",
    ),
    EventDescriptor(
        type_name=ASSISTANT_RETIRED,
        plane=EventPlane.STRUCTURAL,
        domain="event",
        emitter=f"{_ASSISTANT_EMITTER_NAMESPACE}.catalog",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.AUDITOR,
        sensitivity=EventSensitivity.INTERNAL,
        required=ASSISTANT_REQUIRED_FIELDS,
        description="转入 retired 状态，拒收新 run（ADR-0187 §3 D8）",
    ),
)


def all_assistant_event_descriptors() -> tuple[EventDescriptor, ...]:
    """返回闭集内全部 EventDescriptor 元数据（PR-3 注入注册中心）。"""
    return _ASSISTANT_EVENT_DESCRIPTORS


__all__ = [
    "ASSISTANT_BOOTSTRAP_COMPLETED",
    "ASSISTANT_CORDIS_NAMES",
    "ASSISTANT_CREATED",
    "ASSISTANT_EVENT_POINTS",
    "ASSISTANT_JOB_FIRED",
    "ASSISTANT_JOB_REGISTERED",
    "ASSISTANT_PAUSED",
    "ASSISTANT_PROFILE_REVISED",
    "ASSISTANT_REQUIRED_FIELDS",
    "ASSISTANT_RESUMED",
    "ASSISTANT_RETIRED",
    "ASSISTANT_SKILL_ACTIVATED",
    "ASSISTANT_SKILL_EVOLVED_PROMOTED",
    "ASSISTANT_SKILL_EVOLVED_PROPOSED",
    "ASSISTANT_SKILL_INSTALLED",
    "all_assistant_event_descriptors",
]
