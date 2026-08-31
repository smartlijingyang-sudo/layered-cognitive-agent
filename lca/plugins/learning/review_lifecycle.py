"""Profile adapter for candidate-only terminal learning review.

The domain service remains in :mod:`review_service`; this plugin only validates
configuration, exposes the selected service capability, and registers the
service as a passive runtime-lifecycle subscriber.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import (
    LEARNING_FAILURE_ANALYZER,
    LEARNING_REVIEW_SERVICE,
    LEARNING_REVIEW_TICKET_STORE,
    LEARNING_SKILL_ACQUIRER,
    RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.runtime.runtime_lifecycle import (
    RuntimeLifecycleSubscriber,
    RuntimeLifecycleSubscriberContribution,
    RuntimeLifecycleSubscriberRegistry,
)
from lca.contracts.protocols.think.learning import (
    FailureAnalyzer,
    LearningReviewTicketStore,
    SkillAcquirer,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.learning.review_service import (
    LearningReviewAssessment,
    LearningReviewService,
    LearningReviewTicket,
    LearningReviewTicketStatus,
)


class Config(BaseModel):
    """Profile-declared boundaries for terminal learning-review ticket creation."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    statuses: tuple[TaskStatus, ...] = (
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.PARTIAL,
    )
    max_pending: int = Field(default=64, ge=1)
    lease_seconds: int = Field(default=300, ge=1)
    priority: int = Field(default=50, ge=0)

    @field_validator("statuses")
    @classmethod
    def _validate_statuses(cls, statuses: tuple[TaskStatus, ...]) -> tuple[TaskStatus, ...]:
        if not statuses:
            raise ValueError("learning review statuses must not be empty")
        invalid = set(statuses).difference(_REVIEWABLE_STATUSES)
        if invalid:
            values = ", ".join(sorted(status.value for status in invalid))
            raise ValueError(f"learning review statuses must be terminal: {values}")
        return statuses


_REVIEWABLE_STATUSES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.PARTIAL,
        TaskStatus.FAILED,
    }
)


@plugin(
    id="lca-learning-review-lifecycle-subscriber",
    Config=Config,
    provides=[LEARNING_REVIEW_SERVICE.key],
    requires=[
        LEARNING_SKILL_ACQUIRER.key,
        LEARNING_FAILURE_ANALYZER.key,
        LEARNING_REVIEW_TICKET_STORE.key,
        RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key,
    ],
    implements=[RuntimeLifecycleSubscriber],
    layer="L2",
    effects=EffectClass.NONE,
    description="Queue terminal evidence references for candidate-only learning review.",
    test_suite="tests/architecture/test_learning_review_lifecycle.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G4_PERCEPTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-learning-review-lifecycle-subscriber.checked",
                "lca-learning-review-lifecycle-subscriber.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Mount the review service and contribute it as a passive terminal subscriber."""

    if not isinstance(config, Config):
        raise TypeError("learning review lifecycle config must be Config")
    registry = ctx.require(RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key)
    if not isinstance(registry, RuntimeLifecycleSubscriberRegistry):
        raise TypeError(
            "runtime_lifecycle_subscriber_registry must implement "
            "RuntimeLifecycleSubscriberRegistry"
        )
    skill_acquirer = ctx.require(LEARNING_SKILL_ACQUIRER.key)
    if not isinstance(skill_acquirer, SkillAcquirer):
        raise TypeError("learning.skill_acquirer must implement SkillAcquirer")
    failure_analyzer = ctx.require(LEARNING_FAILURE_ANALYZER.key)
    if not isinstance(failure_analyzer, FailureAnalyzer):
        raise TypeError("learning.failure_analyzer must implement FailureAnalyzer")
    ticket_store = ctx.require(LEARNING_REVIEW_TICKET_STORE.key)
    if not isinstance(ticket_store, LearningReviewTicketStore):
        raise TypeError("learning.review_ticket_store must implement LearningReviewTicketStore")

    service = LearningReviewService(
        enabled=config.enabled,
        allowed_statuses=frozenset(config.statuses),
        max_pending=config.max_pending,
        lease_seconds=config.lease_seconds,
        ticket_store=ticket_store,
        skill_acquirer=skill_acquirer,
        failure_analyzer=failure_analyzer,
    )
    ctx.provide(LEARNING_REVIEW_SERVICE.key, service)
    registry.register(
        RuntimeLifecycleSubscriberContribution(
            id="learning-review",
            subscriber=service,
            priority=config.priority,
        )
    )


__all__ = [
    "Config",
    "LearningReviewAssessment",
    "LearningReviewService",
    "LearningReviewTicket",
    "LearningReviewTicketStatus",
    "setup",
]
