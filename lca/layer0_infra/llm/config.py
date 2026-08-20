"""LLM provider identity — one pydantic settings object, two faces.

Env prefix is the public contract: ``LLM_API_KEY`` / ``LLM_MODEL`` /
``LLM_BASE_URL`` / ``LLM_OPENAI_BASE_URL``. Anthropic aliases are accepted.
Generation knobs stay in ``llm_adapter.settings.LLMSettings``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lca.layer0_infra.llm_adapter.factory import load_dotenv_if_present

DEFAULT_CHAT_MODEL = "qwen3.7-plus"


class LLMFace(str, Enum):
    """Which wire a caller needs.

    ``AGENT`` may be Anthropic Messages. ``OPENAI_COMPAT`` is chat/completions
    (housekeeper, embeddings, DSH).
    """

    AGENT = "agent"
    OPENAI_COMPAT = "openai_compat"


class ResolvedEndpoint(BaseModel):
    """Immutable endpoint after face resolution. Callers must not reread env."""

    model_config = ConfigDict(frozen=True)

    face: LLMFace
    api_key: str
    model: str
    base_url: str | None = None

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


class LLMProviderSettings(BaseSettings):
    """Single source for provider identity. Extra LLM_* keys belong to generation."""

    model_config = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    )
    model: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_MODEL", "ANTHROPIC_MODEL"),
    )
    base_url: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_BASE_URL", "ANTHROPIC_BASE_URL"),
    )
    openai_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_OPENAI_BASE_URL"),
    )
    api_style: str = Field(default="", validation_alias=AliasChoices("LLM_API_STYLE"))
    embedding_model: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_EMBEDDING_MODEL"),
    )

    def configured_model(self) -> str:
        return self.model.strip() or DEFAULT_CHAT_MODEL

    def _key(self) -> str:
        return self.api_key.strip()

    def _agent_base(self) -> str | None:
        return self.base_url.strip() or None

    def agent_endpoint(self) -> ResolvedEndpoint:
        return ResolvedEndpoint(
            face=LLMFace.AGENT,
            api_key=self._key(),
            model=self.model.strip(),
            base_url=self._agent_base(),
        )

    def openai_compat_endpoint(self) -> ResolvedEndpoint:
        explicit = self.openai_base_url.strip()
        if explicit:
            base: str | None = explicit
        elif _looks_like_anthropic(self._agent_base()):
            base = None
        else:
            base = self._agent_base()
        return ResolvedEndpoint(
            face=LLMFace.OPENAI_COMPAT,
            api_key=self._key(),
            model=self.model.strip(),
            base_url=base,
        )


# ANTHROPIC_* → LLM_* fill-ins only when the LLM_* key is missing/empty.
_ALIAS_FILLINS: tuple[tuple[str, str], ...] = (
    ("LLM_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    ("LLM_API_KEY", "ANTHROPIC_API_KEY"),
    ("LLM_MODEL", "ANTHROPIC_MODEL"),
    ("LLM_BASE_URL", "ANTHROPIC_BASE_URL"),
)


def normalize_llm_environ() -> None:
    """Fill empty ``LLM_*`` from Anthropic aliases. Never overwrite a set LLM_*."""
    import os

    for llm_key, alias in _ALIAS_FILLINS:
        current = os.environ.get(llm_key, "").strip()
        if current:
            continue
        alias_val = os.environ.get(alias, "").strip()
        if alias_val:
            os.environ[llm_key] = alias_val


def prepare_llm_environ() -> None:
    """Sole process-env prep for LLM credentials: dotenv then alias normalize.

    Owned by the ``lca-llm-resolver`` plugin call path (and by
    ``load_provider_settings`` for non-boot library callers). Gateway/ops
    must not load ``.env`` themselves.
    """
    load_dotenv_if_present()
    normalize_llm_environ()


def load_provider_settings() -> LLMProviderSettings:
    prepare_llm_environ()
    return LLMProviderSettings()


def resolve_endpoint(
    face: LLMFace, settings: LLMProviderSettings | None = None
) -> ResolvedEndpoint:
    cfg = settings if settings is not None else load_provider_settings()
    if face is LLMFace.AGENT:
        return cfg.agent_endpoint()
    return cfg.openai_compat_endpoint()


def configured_chat_model(settings: LLMProviderSettings | None = None) -> str:
    cfg = settings if settings is not None else load_provider_settings()
    return cfg.configured_model()


def llm_credentials() -> tuple[str | None, str | None, str | None]:
    """Agent face as the historical 3-tuple."""
    endpoint = resolve_endpoint(LLMFace.AGENT)
    return _or_none(endpoint.api_key), endpoint.base_url, _or_none(endpoint.model)


def llm_openai_credentials() -> tuple[str | None, str | None, str | None]:
    """OpenAI-compat face as the historical 3-tuple."""
    endpoint = resolve_endpoint(LLMFace.OPENAI_COMPAT)
    return _or_none(endpoint.api_key), endpoint.base_url, _or_none(endpoint.model)


def _or_none(value: str) -> str | None:
    return value or None


def _looks_like_anthropic(base_url: str | None) -> bool:
    if not base_url:
        return False
    from lca.layer0_infra.llm_adapter.openai_compat._anthropic_messages import (
        looks_like_anthropic_base_url,
    )

    return looks_like_anthropic_base_url(base_url)
