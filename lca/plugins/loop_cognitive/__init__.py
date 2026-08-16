"""CognitiveLoopFactory plugin - wraps CognitiveRuntime as AgentLoopFactory."""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.agent import AgentHandle, AgentLoopFactory, AgentOptions, LiveAgent
from lca.contracts.harness.plugin import PluginManifest, PluginKind
from lca.harness.agent.handle import OwnerAgentHandle
from lca.harness.session.inbox import Inbox
from lca.layer4_app.api import Agent

manifest = PluginManifest(
    id="lca.loop.cognitive",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.CONSUMER,
    requires=("brain", "body", "memory", "state_store", "stop_rule", "hooks"),
)


class CognitiveLoopFactory:
    """Factory that creates CognitiveRuntime-based agents.
    
    Implements AgentLoopFactory protocol to allow CognitiveRuntime to be used
    as a pluggable loop provider in the harness spine.
    """

    async def create(
        self,
        scope: Any,
        session_id: str,
        options: AgentOptions,
    ) -> AgentHandle:
        """Create a new agent using CognitiveRuntime.
        
        Args:
            scope: ScopedPluginHost for resolving dependencies
            session_id: Unique session identifier
            options: Agent configuration options
            
        Returns:
            AgentHandle wrapping the created agent
        """
        # Resolve dependencies from scope
        brain = scope.resolve("brain")
        body = scope.resolve("body")
        memory = scope.resolve("memory")
        state_store = scope.resolve("state_store")
        stop_rule = scope.resolve("stop_rule")
        hooks = scope.resolve("hooks")
        session_store = scope.resolve("session_store")
        
        # Create inbox for the agent
        inbox = Inbox(session_store)
        
        # Create Agent using the existing API
        # Note: We need to create an Agent that uses the provided dependencies
        # For now, we'll create a minimal Agent wrapper
        from lca.contracts.models.core.state import AgentState
        from lca.contracts.models.core.budget import Budget
        
        # Create a simple agent that uses the provided components
        agent = Agent(
            role="cognitive",
            goal="",
            backstory="",
            tools=[],
            llm=None,  # Will be provided by brain
            max_steps=options.max_steps or 50,
        )
        
        # Create CognitiveLiveAgent
        from lca.layer4_app.harness_live import CognitiveLiveAgent
        live_agent = CognitiveLiveAgent(
            agent=agent,
            store=session_store,
            inbox=inbox,
            identity_id=session_id,
        )
        
        # Wrap in OwnerAgentHandle
        handle = OwnerAgentHandle(agent=live_agent)
        return handle


def apply(ctx: Any, config: dict[str, Any]) -> None:
    """Register CognitiveLoopFactory in the plugin context."""
    factory = CognitiveLoopFactory()
    ctx.mount("lca.loop.cognitive", factory)
