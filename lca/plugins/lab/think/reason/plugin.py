"""think.reason — messages + tools → LLMResponse via OpenAICompatAdapter.

worker: reason(*, messages, tools, adapter_factory, adapter_kwargs) -> response
kind: TRANSFORMER
out_port: response
config: adapter_factory adapter_kwargs
"""
from typing import Any

from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.think.reason.ops import complete_turn


def reason(
    *,
    messages: Artifact | None,
    tools: Artifact | None,
    adapter_factory: str | None = None,
    adapter_kwargs: dict[str, Any] | None = None,
) -> dict[str, Artifact]:
    """Call LLM via adapter_factory and return response."""
    from lca.infrastructure.llm_adapter.openai_compat import OpenAICompatAdapter

    factory = OpenAICompatAdapter if adapter_factory is None else _import(adapter_factory)
    response = complete_turn(
        messages,
        tools,
        adapter_factory=factory,
        adapter_kwargs=adapter_kwargs or {},
    )
    return {"response": response}


def _import(dotted: str) -> Any:
    """Import a dotted path → attribute."""
    import importlib

    module_path, _, attr = dotted.rpartition(":")
    if not module_path:
        module_path, _, attr = dotted.rpartition(".")
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


__all__ = ["reason"]
