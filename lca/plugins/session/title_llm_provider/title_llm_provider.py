"""first-prompt LLM 标题 provider —— DSH session-title-llm + first-prompt 合体(ADR-0188)。

LCA plugin 硬约束(每 plugin 一个 ``.py``)把 DSH 的共享 LLM 策略包
(``dsh-session-title-llm``)与 first-prompt 节奏包
(``dsh-session-title-first-prompt-llm``)合到本文件:只实现 first-prompt
节奏,共享 DSH 的极简 prompt 骨架(system 指令 + JSON framed 用户消息)。

LLM 能力获取:``ctx.soft_get("llm")`` —— :class:`lca.infrastructure.capability.llm.LlmService`
(``LLMAdapter`` 形态,``complete(prompt, **kwargs) -> LLMResponse``)。组合中无
``llm`` 能力时 provider 仍注册到标题服务,但 ``generate`` 立即上抛,由
``SessionTitleService`` 的 contained 路径静默处理(回退标题保留)。

插件间边界:本 plugin 只经 ``session.title`` capability 交互,不 import
title_service 模块符号;``messages`` 入参 duck-typed(``.seq`` / ``.text``
属性或同名映射形态)。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from pydantic import BaseModel, Field

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_log = structlog.get_logger(__name__)

__all__ = ["Config", "FirstPromptTitleProvider", "build_title_prompt", "setup"]

PROVIDER_ID = "lca.plugins.session.title_llm_provider"


class Config(BaseModel):
    """LLM 标题生成策略;拒绝未知键。"""

    model_config = {"extra": "forbid"}

    target_words: int = Field(default=5, ge=1)
    """标题目标词数(对位 DSH ``targetWords``)。"""

    timeout_ms: int = Field(default=10000, ge=1)
    """单次辅助生成端到端超时毫秒(对位 DSH ``timeoutMs``)。"""

    model: str | None = None
    """可选显式模型 id;非空时透传 ``llm.complete`` kwargs。"""


def _message_fields(message: Any) -> dict[str, Any]:
    """duck-typed message → ``{"seq": int, "text": str}``(不 import 跨插件符号)。"""
    if isinstance(message, Mapping):
        seq, text = message.get("seq"), message.get("text")
    else:
        seq, text = getattr(message, "seq", None), getattr(message, "text", None)
    if isinstance(seq, bool) or not isinstance(seq, int) or not isinstance(text, str):
        raise ValueError("title provider message must carry seq:int and text:str")
    return {"seq": seq, "text": text}


def build_title_prompt(target_words: int, messages: Sequence[dict[str, Any]]) -> str:
    """极简标题 prompt:system 指令 + JSON framed 用户消息。

    对齐 DSH ``systemPrompt`` / ``frameMessages``:指令要求单行纯文本、
    使用消息语言、约 ``target_words`` 词;用户文本以 JSON 数组框定,
    防止其破坏结构定界符。
    """
    instruction = "\n".join(
        (
            "Create a concise title for an AI coding-assistant session "
            "from the supplied human messages.",
            "Return only the title on one line, in plain text of natural language, with no "
            "quotes, prefix, explanation, Markdown, XML, or terminal control codes. "
            "No code is allowed.",
            "Use the language of the messages.",
            f"Aim for about {target_words} words.",
        )
    )
    framed = json.dumps(list(messages), ensure_ascii=False)
    return f"{instruction}\n\nGenerate the session title from this JSON array of human messages:\n{framed}"


class FirstPromptTitleProvider:
    """first-prompt 节奏标题 provider:取首条合格用户消息,经 LLM 生成标题。

    失败语义:llm 能力缺席 / 消息为空 / 超时 / LLM 异常全部上抛,由
    ``SessionTitleService`` 统一 contained(回退标题保留,不阻塞主响应)。
    """

    id: str = PROVIDER_ID
    automatic: str = "first-prompt"

    def __init__(self, llm: Any, config: Config | None = None) -> None:
        """构造 provider;``llm`` 为 ``None`` 表示组合中无 LLM 能力。"""
        self._llm = llm
        self._config = config or Config()

    async def generate(
        self,
        session: Any,
        messages: Sequence[Any],
        signal: asyncio.Event,
    ) -> dict[str, Any]:
        """产出一次标题修订:``{title, message_seqs, model?}``。

        超时:``config.timeout_ms`` 经 :func:`asyncio.wait_for`;取消:由
        服务侧 ``Task.cancel`` 表达(``wait_for`` 内透传),``signal`` 仅为
        协作式探测。first-prompt 不需要 DSH 的主请求路由 provenance。
        """
        del session, signal
        if self._llm is None:
            raise RuntimeError("session-title-llm: llm capability is not provided")
        if not messages:
            raise ValueError("session-title-llm: at least one source message is required")
        first = _message_fields(messages[0])
        prompt = build_title_prompt(self._config.target_words, [first])
        kwargs: dict[str, Any] = {}
        if self._config.model:
            kwargs["model"] = self._config.model
        response = await asyncio.wait_for(
            self._llm.complete(prompt, **kwargs),
            timeout=self._config.timeout_ms / 1000,
        )
        model = getattr(response, "model", "") or None
        return {
            "title": getattr(response, "text", ""),
            "message_seqs": [first["seq"]],
            "model": model,
        }


# ── plugin manifest ────────────────────────────────────────────────────


@plugin(
    id="lca.plugins.session.title_llm_provider",
    provides=["session.title.provider"],
    requires=["session.title"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="network",
    description=(
        "first-prompt LLM 标题 provider(ADR-0188):DSH session-title-llm + "
        "first-prompt 合体。经 ctx.soft_get 软查 llm capability(缺席时 generate "
        "静默失败,回退保留);经 requires 授权注册到 session.title 服务。"
        "effects=network(LLM 远端调用;本仓 EffectClass 无 llm:call 档)。"
    ),
    test_suite="tests/plugins/session/test_title_llm_provider.py",
    functional_group=FunctionalGroup.G3_FACTS,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G3_FACTS),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.title", "llm"),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """构造 provider 并注册到 ``session.title`` 服务。

    失败语义:``session.title`` 服务缺席时只 provide 不注册(记日志);
    ``llm`` capability 缺席时 provider 照常注册,``generate`` 运行时上抛
    并由服务 contained。
    """
    provider = FirstPromptTitleProvider(ctx.soft_get("llm"), config)
    ctx.provide("session.title.provider", provider)
    service = ctx.soft_get("session.title")
    if service is None:
        _log.info("session.title.provider.no_service", id=PROVIDER_ID)
        return
    service.register_provider(provider)
