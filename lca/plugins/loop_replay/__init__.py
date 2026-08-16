"""ReplayLoopFactory plugin - deterministic replay from golden journal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.harness.agent import AgentHandle, AgentOptions, LiveAgent, MessageReceipt, UserMessage
from lca.contracts.harness.plugin import PluginManifest, PluginKind
from lca.contracts.harness.session import SessionEvent
from lca.harness.session.store import SessionStore


manifest = PluginManifest(
    id="lca.loop.replay",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.CONSUMER,
    requires=("session_store",),
)


@dataclass
class ReplayLiveAgent:
    """LiveAgent that replays events from a golden journal.
    
    This agent doesn't actually call the LLM or execute tools.
    Instead, it reads pre-recorded events from the session journal
    and returns them as if they were fresh responses.
    """
    
    session_store: SessionStore
    session_id: str
    
    @property
    def id(self) -> str:
        return f"replay-{self.session_id}"
    
    @property
    def status(self) -> str:
        return "idle"
    
    async def replay_all(self) -> list[SessionEvent]:
        """Replay all events from journal in seq order.

        Returns:
            All recorded SessionEvents sorted by ascending seq.
        """
        events = await self.session_store.read_from(0)
        return sorted(events, key=lambda e: e.seq)

    async def followup(self, message: UserMessage) -> MessageReceipt:
        """Return the next recorded response from the journal.

        Args:
            message: User message (ignored in replay mode)

        Returns:
            MessageReceipt with replayed content
        """
        events = await self.replay_all()

        for event in events:
            if event.type == "message.accepted.v1" and event.data.get("role") == "assistant":
                return MessageReceipt(
                    message_id=event.data.get("message_id", ""),
                    session_id=self.session_id,
                    seq=event.seq,
                )

        # No recorded response found
        return MessageReceipt(
            message_id="",
            session_id=self.session_id,
            seq=-1,
        )
    
    async def steer(self, message: UserMessage) -> MessageReceipt:
        """Replay doesn't support steering."""
        return MessageReceipt(
            message_id="",
            session_id=self.session_id,
            seq=-1,
        )
    
    async def inject(self, message: UserMessage) -> MessageReceipt:
        """Replay doesn't support injection."""
        return MessageReceipt(
            message_id="",
            session_id=self.session_id,
            seq=-1,
        )
    
    def cancel(self, reason: str = "user", *, keep_inbox: bool = True) -> None:
        """Cancel is a no-op in replay mode."""
        pass
    
    async def when_idle(self) -> None:
        """Replay is always idle."""
        pass


class ReplayLoopFactory:
    """Factory that creates replay agents from golden journals.
    
    This factory creates agents that replay pre-recorded sessions
    instead of actually executing the cognitive loop.
    """
    
    async def create(
        self,
        scope: Any,
        session_id: str,
        options: AgentOptions,
    ) -> AgentHandle:
        """Create a replay agent for the given session.
        
        Args:
            scope: ScopedPluginHost for resolving dependencies
            session_id: Session ID to replay
            options: Agent options (ignored in replay mode)
            
        Returns:
            AgentHandle wrapping the replay agent
        """
        from lca.harness.agent.handle import OwnerAgentHandle
        
        session_store = scope.resolve("session_store")
        
        # Create replay agent
        replay_agent = ReplayLiveAgent(
            session_store=session_store,
            session_id=session_id,
        )
        
        # Wrap in OwnerAgentHandle
        handle = OwnerAgentHandle(agent=replay_agent)
        return handle


def apply(ctx: Any, config: dict[str, Any]) -> None:
    """Register ReplayLoopFactory in the plugin context."""
    factory = ReplayLoopFactory()
    ctx.mount("lca.loop.replay", factory)
