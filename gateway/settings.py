"""Gateway 全局配置 —— pydantic-settings 驱动（env 前缀 ``LCA_GW_``，读 .env）。

CORS、上传限制、SSE 缓冲等运行时参数统一在此管理，
禁止在路由处理函数中硬编码（AGENTS.md 约定）。
"""

from __future__ import annotations

from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_CORS_ORIGINS = "*"
_DEFAULT_CORS_METHODS = "GET, POST, OPTIONS"
_DEFAULT_CORS_HEADERS = "Content-Type, Last-Event-ID, Authorization"
_DEFAULT_CORS_EXPOSE = "Content-Type, Content-Disposition"

_DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_DEFAULT_MAX_BUFFERED_FRAMES = 4096
_DEFAULT_MAX_SUBSCRIBER_QUEUE = 256

MIB: Final[int] = 1024 * 1024


class GatewaySettings(BaseSettings):
    """Gateway HTTP/运行时配置。

    - ``cors_origins``：允许的来源（``*`` 或逗号分隔列表）；
    - ``max_upload_bytes``：附件上传大小上限；
    - ``max_buffered_frames``：SSE 帧环形缓冲区容量；
    - ``max_subscriber_queue``：每个 SSE 订阅者的 asyncio.Queue 容量。
    """

    model_config = SettingsConfigDict(
        env_prefix="LCA_GW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cors_origins: str = Field(
        default=_DEFAULT_CORS_ORIGINS,
        description="Comma-separated allowed origins, or '*' for any.",
    )
    cors_methods: str = Field(
        default=_DEFAULT_CORS_METHODS,
        description="Comma-separated allowed HTTP methods.",
    )
    cors_headers: str = Field(
        default=_DEFAULT_CORS_HEADERS,
        description="Comma-separated allowed request headers.",
    )
    cors_expose_headers: str = Field(
        default=_DEFAULT_CORS_EXPOSE,
        description="Comma-separated exposed response headers.",
    )
    max_upload_bytes: int = Field(
        default=_DEFAULT_MAX_UPLOAD_BYTES,
        ge=1,
        description="Maximum attachment upload size in bytes.",
    )
    max_buffered_frames: int = Field(
        default=_DEFAULT_MAX_BUFFERED_FRAMES,
        ge=16,
        description="SSE ring-buffer capacity per run session.",
    )
    max_subscriber_queue: int = Field(
        default=_DEFAULT_MAX_SUBSCRIBER_QUEUE,
        ge=8,
        description="asyncio.Queue maxsize per SSE subscriber.",
    )

    def cors_headers_dict(self) -> dict[str, str]:
        """Build CORS response headers dict."""
        return {
            "Access-Control-Allow-Origin": self.cors_origins,
            "Access-Control-Allow-Methods": self.cors_methods,
            "Access-Control-Allow-Headers": self.cors_headers,
            "Access-Control-Expose-Headers": self.cors_expose_headers,
        }

    def allowed_origins_list(self) -> list[str]:
        """Parse comma-separated origins into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


_settings: GatewaySettings | None = None


def gateway_settings() -> GatewaySettings:
    """Return the cached singleton (lazy-init)."""
    global _settings
    if _settings is None:
        _settings = GatewaySettings()
    return _settings


def reset_gateway_settings() -> None:
    """Reset the singleton (test only)."""
    global _settings
    _settings = None
