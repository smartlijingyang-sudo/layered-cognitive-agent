"""first-prompt LLM 标题 provider plugin(ADR-0188)。

DSH ``session-title-llm`` + ``session-title-first-prompt-llm`` 合体
(LCA 每 plugin 一个 ``.py`` 约束)。plugin 装配入口是
:mod:`lca.plugins.session.title_llm_provider.title_llm_provider`
(``@plugin`` 唯一入口,本 ``__init__`` 不声明 plugin)。
"""

from lca.plugins.session.title_llm_provider.title_llm_provider import (
    Config,
    FirstPromptTitleProvider,
    build_title_prompt,
)

__all__ = ["Config", "FirstPromptTitleProvider", "build_title_prompt"]
