"""DSH process knobs. Model/key/url come from ``llm.config``, not DSH_*."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lca.layer0_infra.llm.config import LLMFace, configured_chat_model, resolve_endpoint
from lca.layer0_infra.llm_adapter.settings import get_llm_settings


class DshSettings(BaseSettings):
    """Harness launch only. Identity is ``resolve_endpoint(OPENAI_COMPAT)``."""

    model_config = SettingsConfigDict(
        env_prefix="DSH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: str = "deepseek-official"
    cwd: str = ""
    cordis: str = ""
    system_prompt: str = ""
    request_timeout_seconds: float = Field(default=180.0, gt=0)

    def resolved_model(self) -> str:
        return configured_chat_model()

    def resolved_api_key(self) -> str:
        return resolve_endpoint(LLMFace.OPENAI_COMPAT).api_key

    def resolved_base_url(self) -> str:
        return resolve_endpoint(LLMFace.OPENAI_COMPAT).base_url or ""

    def resolved_max_tokens(self) -> int | None:
        return get_llm_settings().max_tokens

    def resolved_cordis(self) -> str | None:
        path = self.cordis.strip()
        if not path:
            return None
        return str(Path(path).expanduser())
