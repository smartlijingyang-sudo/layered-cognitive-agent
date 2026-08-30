"""Human-answer resume input adapter plugin.

The plugin registers the existing normalization behavior as a named capability.
Production assembly selects it through ``AgentSpec`` rather than directly
constructing a concrete runtime adapter.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import RESUME_INPUT_ADAPTERS
from lca.contracts.protocols.session.resume_input import ResumeInputAdapter
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.runtime.resume_input import HumanAnswerResumeInputAdapter


class Config(BaseModel):
    """No configuration is required for the standard human-answer adapter."""

    model_config = {"extra": "forbid"}


def build_human_answer_resume_input_adapter() -> ResumeInputAdapter:
    """Build the standard adapter that records a human answer as a turn."""

    return HumanAnswerResumeInputAdapter()


@plugin(
    id="resume_input.human_answer",
    provides=[],
    requires=[RESUME_INPUT_ADAPTERS.key],
    implements=[ResumeInputAdapter],
    layer="L2",
    effects="none",
    description=(
        "Register the standard human-answer adapter as resume_input_adapters['human_answer']."
    ),
    test_suite="tests/runtime/test_resume_input.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register the default resume-input normalization strategy."""

    del config
    ctx.register(
        RESUME_INPUT_ADAPTERS.key,
        "human_answer",
        build_human_answer_resume_input_adapter,
    )
