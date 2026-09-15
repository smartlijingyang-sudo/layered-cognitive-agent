"""M0 — Event hub fanout contract.

调度层: SPINE EP → observer capability key 的 1:1 映射。
- 一个 EP 最多路由到一个 observer(no chain fan-out)。
- 一个 observer 至多被一个 EP 触发(no double emit)。
- 装载期 model_validator 静态校验 bijective,违反抛 EventHubConfigError。
- 13 个 observer 自身不感知 hub 存在 —— hub 只订阅,不重写 emit 路径。

Producers: observation.event_hub plugin
Consumers: Session.append 单轨(由 observer 内部 publish_ep_bound 触发,hub 不参与)
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator


class EventHubConfigError(ValueError):
    """bijective 校验失败时抛 —— 装载期 fail-loud。"""


def validate_fanout_table(
    rules: tuple[FanoutRule, ...],
) -> None:
    """纯函数:校验 `rules` 是否 bijective。

    边界入口(profile resolve 装载期)调用此函数获得 first-class
    `EventHubConfigError`;`EventHubConfig` 的 model_validator 保留
    作为构造期的兜底。
    """
    seen_eps: set[str] = set()
    seen_observers: set[str] = set()
    for rule in rules:
        if rule.ep in seen_eps:
            raise EventHubConfigError(f"duplicate ep in fanout table: {rule.ep!r}")
        seen_eps.add(rule.ep)
        if rule.observer_capability in seen_observers:
            raise EventHubConfigError(
                f"duplicate observer_capability in fanout table: {rule.observer_capability!r}"
            )
        seen_observers.add(rule.observer_capability)


class FanoutRule(BaseModel):
    """单条 EP → observer capability 映射。

    一个 SPINE EP 至多触发一个 observer capability(避免 fan-out 链)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ep: str
    observer_capability: str
    enabled: bool = True


class EventHubConfig(BaseModel):
    """EventHub 完整配置 = FanoutRule 集合。

    `rules` 必须 bijective:
    - 每个 `ep` 至多出现一次(否则一 EP 触发多 observer → fan-out 链)
    - 每个 `observer_capability` 至多出现一次(否则 observer 被多个 EP 触发 → 重复 emit)

    优先用 `validate_fanout_table(rules)` 在装载期获得 first-class
    `EventHubConfigError`;直接构造 `EventHubConfig` 会得到 pydantic
    `ValidationError`(消息里仍包含原始错误文本)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rules: tuple[FanoutRule, ...] = ()

    @model_validator(mode="after")
    def _validate_one_to_one(self) -> EventHubConfig:
        validate_fanout_table(self.rules)
        return self


__all__ = [
    "EventHubConfig",
    "EventHubConfigError",
    "FanoutRule",
    "validate_fanout_table",
]

