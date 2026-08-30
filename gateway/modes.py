"""Gateway 协作模式目录 —— UI 与生产组队的单一事实源（ADR-0052）。

Solo/Team 分治：solo 是裸模型（零角色概念，对齐 LobeHub 默认 agent），
team 走 LLM casting（ADR-0042）。本模块只定义 team 模式的 UI 元数据；
solo 不进 MODE_DEFINITIONS，由 run_executor 直接构造。

测试 CLI 探针（``tests/harness/modes.py``）保留 Alice/Bob 剧本用于确定性探针；
本模块定义面向真实用户的产品文案。

Mode 分派（ADR-0076 §六）：``resolve_lca_mode()`` 不再做字符串
``if/elif``；它读取由 :mod:`lca.plugins.seams.state.run_mode_registry`
提供的 ``RunModeRegistry``，每个 mode（solo / team / cordis-creator / 未来
research / code / creator 变体）由 ``ModeAdapter`` plugin 注册。无 ctx 时
退化为稳定的 ``_FALLBACK_KEY_MAP``，保持与现有 OpenAI shim / 测试契约
一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from lca.contracts.capabilities import RUN_MODE_REGISTRY
from lca.contracts.mechanisms.capability import require_capability

if TYPE_CHECKING:
    from lca.plugins.seams.state.run_mode_registry import RunModeRegistry


@dataclass(frozen=True)
class ModeDefinition:
    """一种协作模式的 UI 元数据。"""

    key: str
    help_text: str
    example_prompts: tuple[str, ...]


MODE_DEFINITIONS: Final[dict[str, ModeDefinition]] = {
    "team": ModeDefinition(
        key="team",
        help_text="团队 · 系统按任务自动组队和分工",
        example_prompts=(
            "给新功能写发布文案并评估技术风险",
            "制定季度产品路线图的关键里程碑",
            "从效率、协作、文化三个角度分析远程办公",
            "是否应在本周发布灰度版本？",
        ),
    ),
}

ALL_MODES: Final[tuple[str, ...]] = tuple(MODE_DEFINITIONS.keys())

MODE_HELP: Final[dict[str, str]] = {
    key: definition.help_text for key, definition in MODE_DEFINITIONS.items()
}

EXAMPLE_PROMPTS: Final[dict[str, tuple[str, ...]]] = {
    key: definition.example_prompts for key, definition in MODE_DEFINITIONS.items()
}

DEFAULT_MODE: Final[str] = "solo"

LCA_UI_MODELS: Final[tuple[str, ...]] = ("solo", "team", "auto", "cordis-creator")
"""LobeHub 模型选择器唯一对外的入口。真实 LLM / agent persona 由 gateway 解析。

- ``solo``    —— 默认独享 agent（web-standard profile 的 default role）
- ``team``    —— LLM casting 自动组队（ADR-0042）
- ``auto``    —— 同 team（显式别名）
- ``cordis-creator`` —— Creator §13.3 自 plugin 创作 persona；同一 web-standard
  profile 上下文，工具集由 cordis-creator role 的 manifest 限定为
  ``cordis_control / file_write / bash`` 三件。
"""

SOLO_MODE_KEY: Final[str] = "solo"
"""Solo 入口：裸模型，零角色概念，不进 MODE_DEFINITIONS（ADR-0052）。"""

CORDIS_CREATOR_MODE_KEY: Final[str] = "cordis-creator"
"""Creator 入口：cordis-creator persona + 创作工具集（single-port 多 persona）。"""

SOLO_ROLE: Final[str] = "助手"
"""Solo agent 的 role 标签 —— 纯展示用，不影响行为（对齐 LobeHub systemRole=''）。"""

CORDIS_CREATOR_ROLE: Final[str] = "cordis-creator"
"""Creator persona 的 role tag；与 profile.cordis-creator.yaml 的 role 字段一致。"""


_FALLBACK_KEY_MAP: Final[dict[str, str]] = {
    "team": "team",
    "auto": "team",
    "cordis-creator": "cordis-creator",
    "solo": "solo",
}
"""ADR-0076 §六: 无 ctx 时的稳定降级映射。

调用方传入 ``registry=None`` 或在 ctx 未挂载 ``run_mode_registry`` 的
测试 profile 下，``resolve_lca_mode`` 走这张表；命中失败则回到
``SOLO_MODE_KEY``。该表以 module-level 静态数据出现，**不参与任何
``if/elif`` 分支**；substitution gate ``test_substitution_gates.py``
显式豁免此文件（见 ``ALLOWED_FILES_FOR_KEY_DISPATCH``）。
"""


_CREATOR_MODE_KEYS: Final[frozenset[str]] = frozenset({CORDIS_CREATOR_MODE_KEY})
"""Set of mode keys whose default persona is the cordis-creator (ADR-0076 §六).

Used by :func:`is_cordis_creator_mode` and :func:`resolve_agent_role`
to translate a resolved mode key into persona-level facts.  Membership
tests are O(1) and never expand to ``if/elif`` branching on the key.
"""


def resolve_lca_mode(
    model: str,
    *,
    registry: RunModeRegistry | None = None,
) -> str:
    """Map OpenAI model id → LCA gateway mode ('solo' / 'team' / 'cordis-creator')。

    - ``registry`` 提供时：走 ``registry.resolve(model)``，每个 mode
      adapter 自行声明 ``matches`` 谓词。Adapter 是插件；新增 mode
      不需要修改本函数（ADR-0076 §六 替换测试）。
    - ``registry=None`` 时：走 ``_FALLBACK_KEY_MAP``（向后兼容 OpenAI
      shim 与未加载 profile 的探针）；未命中返回 ``SOLO_MODE_KEY``。
    """

    key = (model or "").strip().lower()
    if registry is not None:
        try:
            return registry.resolve(key).key
        except LookupError:
            return SOLO_MODE_KEY
    return _FALLBACK_KEY_MAP.get(key, SOLO_MODE_KEY)


def resolve_profile_mode(ctx: object, model: str) -> str:
    """Resolve a gateway mode from the profile-owned registry.

    This is the production ingress: a booted profile must provide the
    ``run_mode_registry`` capability.  It intentionally does not consult the
    static compatibility map, so a missing mode binding fails before a request
    can select an implementation outside the compiled plugin tree.

    ``resolve_lca_mode`` remains available for isolated probes and compatibility
    callers that deliberately have no profile context.
    """

    registry = require_capability(ctx, RUN_MODE_REGISTRY.key)
    return resolve_lca_mode(model, registry=registry)


def is_cordis_creator_mode(
    model: str,
    *,
    registry: RunModeRegistry | None = None,
) -> bool:
    """model 是否是 cordis-creator（前端发来 "cordis-creator" 时返回 True）。"""

    return _resolved_mode_key(model, registry=registry) in _CREATOR_MODE_KEYS


def resolve_agent_role(
    model: str,
    *,
    registry: RunModeRegistry | None = None,
) -> str:
    """Map model → agent role tag for :class:`Agent` + :class:`RoleProfile`。

    - ``cordis-creator`` → ``cordis-creator``（Creator §13.3 persona）
    - 其它 → ``SOLO_ROLE``（默认助手 persona）

    When a registry is mounted the role tag comes from
    :attr:`ModeAdapter.role` (registry-driven path); otherwise the
    fallback mode key is consulted via the static lookup table.
    """

    if registry is not None:
        try:
            return registry.resolve(model).role or SOLO_ROLE
        except LookupError:
            return SOLO_ROLE
    if _resolved_mode_key(model, registry=registry) in _CREATOR_MODE_KEYS:
        return CORDIS_CREATOR_ROLE
    return SOLO_ROLE


def _resolved_mode_key(
    model: str,
    *,
    registry: RunModeRegistry | None,
) -> str:
    """Internal: compute the resolved mode key without exposing it to callers.

    Uses the registry when present, otherwise the static
    :data:`_FALLBACK_KEY_MAP`.  Result is always a mode key string and
    is the single funnel for :func:`is_cordis_creator_mode` and
    :func:`resolve_agent_role`, so neither function performs its own
    string compare (ADR-0076 §六 substitution gate).
    """

    if registry is not None:
        try:
            return registry.resolve(model).key
        except LookupError:
            return SOLO_MODE_KEY
    return _FALLBACK_KEY_MAP.get((model or "").strip().lower(), SOLO_MODE_KEY)
