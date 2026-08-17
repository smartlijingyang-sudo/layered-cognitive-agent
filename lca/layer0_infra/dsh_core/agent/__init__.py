"""1:1 port of ``@deepseek-ai/dsh-agent/index.ts``.

Re-exports the entire public agent API surface.
"""

from __future__ import annotations

# -- consumed-work --
from lca.layer0_infra.dsh_core.agent.consumed_work import (
    ConsumedWork,
    fold_consumed_work,
)

# -- dispatch --
from lca.layer0_infra.dsh_core.agent.dispatch import (
    AgentEventDispatch,
    AssembleContext,
    agent_carrier,
    agent_events,
    assemble_context_for,
    emit_agent_event,
)

# -- inbox --
from lca.layer0_infra.dsh_core.agent.inbox import (
    Inbox,
    InboxNotifications,
)

# -- index (AgentRegistry) --
from lca.layer0_infra.dsh_core.agent.index import (
    AgentFactory,
    AgentHandle,
    AgentRegistry,
    AgentSetup,
    AgentSetupCommit,
    CreateAgentOptions,
    ResumeAgentOptions,
)

# -- model-selection --
from lca.layer0_infra.dsh_core.agent.model_selection import (
    ModelSelection,
    ModelSelectionRef,
    install_model_selection,
)

# -- runtime-types (re-export everything) --
from lca.layer0_infra.dsh_core.agent.runtime_types import (
    EVENT_AGENT_CREATED,
    EVENT_AGENT_DISPOSED,
    EVENT_AGENT_ERROR,
    EVENT_AGENT_INBOX_CLAIMED,
    EVENT_AGENT_INBOX_DISCARDED,
    EVENT_AGENT_INBOX_INSERTED,
    EVENT_AGENT_PRE_STEP,
    EVENT_AGENT_REQUEST,
    EVENT_AGENT_REQUEST_ERROR,
    EVENT_AGENT_SESSION_START,
    EVENT_AGENT_STATUS,
    EVENT_AGENT_TURN_STOPPING,
    Agent,
    AgentCancelCause,
    AgentCreatedPayload,
    AgentDisposedPayload,
    AgentErrorPayload,
    AgentInboxClaimedPayload,
    AgentInboxDiscardedPayload,
    AgentInboxInsertedPayload,
    AgentOptions,
    AgentPreStepPayload,
    AgentRequestErrorPayload,
    AgentRequestPayload,
    AgentSessionStartPayload,
    AgentStatus,
    AgentStatusPayload,
    AgentTurnStoppingPayload,
    CancelOptions,
    PreStepDecision,
    RequestErrorAction,
    SessionStartSource,
    pre_step_enter,
    pre_step_reject,
    retry_action,
)

# -- types --
from lca.layer0_infra.dsh_core.agent.types import (
    InboxSplicedPayload,
    InboxTarget,
)

__all__ = [
    # event names
    "EVENT_AGENT_CREATED",
    "EVENT_AGENT_DISPOSED",
    "EVENT_AGENT_ERROR",
    "EVENT_AGENT_INBOX_CLAIMED",
    "EVENT_AGENT_INBOX_DISCARDED",
    "EVENT_AGENT_INBOX_INSERTED",
    "EVENT_AGENT_PRE_STEP",
    "EVENT_AGENT_REQUEST",
    "EVENT_AGENT_REQUEST_ERROR",
    "EVENT_AGENT_SESSION_START",
    "EVENT_AGENT_STATUS",
    "EVENT_AGENT_TURN_STOPPING",
    # runtime types
    "Agent",
    "AgentCancelCause",
    # event payloads
    "AgentCreatedPayload",
    "AgentDisposedPayload",
    "AgentErrorPayload",
    # dispatch
    "AgentEventDispatch",
    # registry
    "AgentFactory",
    "AgentHandle",
    "AgentInboxClaimedPayload",
    "AgentInboxDiscardedPayload",
    "AgentInboxInsertedPayload",
    "AgentOptions",
    "AgentPreStepPayload",
    "AgentRegistry",
    "AgentRequestErrorPayload",
    "AgentRequestPayload",
    "AgentSessionStartPayload",
    "AgentSetup",
    "AgentSetupCommit",
    "AgentStatus",
    "AgentStatusPayload",
    "AgentTurnStoppingPayload",
    "AssembleContext",
    "CancelOptions",
    # consumed work
    "ConsumedWork",
    "CreateAgentOptions",
    # inbox
    "Inbox",
    "InboxNotifications",
    # types
    "InboxSplicedPayload",
    "InboxTarget",
    # model selection
    "ModelSelection",
    "ModelSelectionRef",
    "PreStepDecision",
    "RequestErrorAction",
    "ResumeAgentOptions",
    "SessionStartSource",
    "agent_carrier",
    "agent_events",
    "assemble_context_for",
    "emit_agent_event",
    "fold_consumed_work",
    "install_model_selection",
    "pre_step_enter",
    "pre_step_reject",
    "retry_action",
]
