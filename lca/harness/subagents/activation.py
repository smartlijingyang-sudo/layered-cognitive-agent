"""Lifecycle owner for activated subagents."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.agent import AgentIdentity, AgentOptions
from lca.contracts.harness.subagent import (
    ActivatedSubagent,
    SubagentActivator,
    SubagentRequest,
)
from lca.harness.subagents.registry import SubagentRegistry


class ActivationManager:
    """Negotiates child activation and owns child cancellation/draining."""

    def __init__(self, registry: SubagentRegistry, activator: SubagentActivator) -> None:
        self._registry = registry
        self._activator = activator
        self._children: dict[str, dict[str, ActivatedSubagent]] = {}

    async def activate(self, request: SubagentRequest) -> ActivatedSubagent:
        spec = self._registry.get(request.name)
        capabilities = spec.capabilities
        if not request.required_capabilities <= capabilities.capabilities:
            raise PermissionError("subagent does not provide all required capabilities")
        if request.parent.delegation_depth >= capabilities.max_delegation_depth:
            raise PermissionError("subagent delegation depth limit reached")
        if capabilities.tools_allow and not request.requested_tools <= capabilities.tools_allow:
            raise PermissionError("requested tools are not allowed for subagent")
        if request.requested_tools & capabilities.tools_deny:
            raise PermissionError("requested tools are denied for subagent")

        child_identity = AgentIdentity(
            session_id=new_id("sub"),
            parent_session=request.parent.session_id,
            delegation_depth=request.parent.delegation_depth + 1,
            origin="subagent",
        )
        options = self._effective_options(
            request.options,
            request.requested_tools,
            capabilities.tools_allow,
            capabilities.tools_deny,
        )
        handle = await self._activator(spec, child_identity, options)
        activated = ActivatedSubagent(child_identity, handle, capabilities)
        self._children.setdefault(request.parent.session_id, {})[child_identity.session_id] = (
            activated
        )
        return activated

    def children_of(self, parent_session: str) -> tuple[ActivatedSubagent, ...]:
        return tuple(self._children.get(parent_session, {}).values())

    async def cancel_child(
        self, parent_session: str, child_session: str, reason: str = "parent"
    ) -> None:
        child = self._children.get(parent_session, {}).get(child_session)
        if child is not None:
            await child.handle.dispose(reason)
            self._remove_child(parent_session, child_session)

    async def cancel_children(self, parent_session: str, reason: str = "parent") -> None:
        children = self.children_of(parent_session)
        results = await asyncio.gather(
            *(child.handle.dispose(reason) for child in children), return_exceptions=True
        )
        for child, result in zip(children, results, strict=True):
            if not isinstance(result, BaseException):
                self._remove_child(parent_session, child.identity.session_id)
        errors = [result for result in results if isinstance(result, BaseException)]
        if errors:
            raise errors[0]

    async def drain_parent(self, parent_session: str, *, timeout_s: float = 30.0) -> None:
        """Wait for all children before a parent session may be disposed."""
        children = self.children_of(parent_session)
        for child in children:
            child.handle.agent.cancel("parent_drain")
        with suppress(TimeoutError):
            await asyncio.wait_for(
                asyncio.gather(*(child.handle.agent.when_idle() for child in children)),
                timeout=timeout_s,
            )
        await self.cancel_children(parent_session, "parent_drain")

    def _remove_child(self, parent_session: str, child_session: str) -> None:
        children = self._children.get(parent_session)
        if children is None:
            return
        children.pop(child_session, None)
        if not children:
            self._children.pop(parent_session, None)

    @staticmethod
    def _effective_options(
        options: AgentOptions,
        requested_tools: frozenset[str],
        allowed: frozenset[str],
        denied: frozenset[str],
    ) -> AgentOptions:
        requested = requested_tools or frozenset(options.tools_allow or ())
        if requested_tools and allowed and not requested_tools <= allowed:
            raise PermissionError("requested tools are not allowed for subagent")
        # An allowlist-bearing provider must never produce an unrestricted child.
        tools_allow = (
            tuple(sorted(requested or allowed)) if allowed else tuple(sorted(requested)) or None
        )
        tools_deny = tuple(sorted(set(options.tools_deny or ()) | denied)) or None
        return AgentOptions(
            provider=options.provider,
            model=options.model,
            max_steps=options.max_steps,
            max_tokens=options.max_tokens,
            tools_allow=tools_allow,
            tools_deny=tools_deny,
        )
