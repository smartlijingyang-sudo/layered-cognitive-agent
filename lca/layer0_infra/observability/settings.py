"""可观测性配置 —— pydantic-settings 驱动（env 前缀 LCA_OBS_，读 .env）。

配置项全部走环境变量/`.env`，禁止代码内硬编码（AGENTS.md 约定）。
Langfuse 凭据兼容官方 ``LANGFUSE_*`` 变量名。
"""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lca.layer0_infra.observability.policy import Verbosity

_DEFAULT_BACKENDS = "console"
_DEFAULT_JSONL_PATH = "traces/lca_journal.jsonl"
_DEFAULT_LANGFUSE_HOST = "http://localhost:3000"


class ObservabilitySettings(BaseSettings):
    """可观测性子系统配置。

    - ``backends``：``+`` 或 ``,`` 分隔的导出器名（console/jsonl/langfuse/memory）；
    - ``verbosity``：信息量档位 minimal|standard|verbose；
    - ``sampling_rate``：头采样率 0.0~1.0（verbose 大流量调试可降采样）；
    - ``redact_enabled``：脱敏兜底开关（生产环境不应关闭）。
    """

    model_config = SettingsConfigDict(
        env_prefix="LCA_OBS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backends: str = _DEFAULT_BACKENDS
    verbosity: Verbosity = Verbosity.STANDARD
    sampling_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    jsonl_path: str = _DEFAULT_JSONL_PATH
    redact_enabled: bool = True

    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("LCA_OBS_ENVIRONMENT", "LANGFUSE_ENVIRONMENT"),
    )

    langfuse_public_key: str = Field(
        default="",
        validation_alias=AliasChoices("LCA_OBS_LANGFUSE_PUBLIC_KEY", "LANGFUSE_PUBLIC_KEY"),
    )
    langfuse_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("LCA_OBS_LANGFUSE_SECRET_KEY", "LANGFUSE_SECRET_KEY"),
    )
    langfuse_host: str = Field(
        default=_DEFAULT_LANGFUSE_HOST,
        validation_alias=AliasChoices(
            "LCA_OBS_LANGFUSE_HOST", "LANGFUSE_HOST", "LANGFUSE_BASE_URL"
        ),
    )

    def backend_names(self) -> list[str]:
        """解析 backends 字符串为导出器名列表（空串 → 空列表）。"""
        text = self.backends.replace(",", "+")
        return [part.strip() for part in text.split("+") if part.strip()]
