"""assistant.ownership 插件 —— ADR-0252 D2/D3。

提供 ``assistant.ownership`` capability：用户↔助理归属关系的持久化面
（LCA 自有数据库）。同时把 store 安装到 ``app.state.assistant_ownership``
供 ``routes_assistants`` / ``routes_onboarding`` / run 归属检查读取。

配置：

- ``database_url`` —— 仅来自 Profile ``{from_env: LCA_DATABASE_URL}``
  required:false；空字符串 = SQLite（``~/.lca/lca.sqlite3``）。
- ``dev_mode`` —— ``True`` 时归属检查放行（映射 ``local-dev-user``），
  保持存量单用户行为；``False`` 时缺身份返回 401（fail-closed）。
- ``expected_token`` —— 只经 ``{from_env: LCA_AUTH_EXPECTED_TOKEN}`` 注入。
  **没有公开默认值**：``dev_mode=False`` 且注入为空时 setup fail-loud，
  避免"门装上、钥匙挂门上"。

插件代码禁止直接读 ``os.environ``（ADR-0202 纪律）。
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import ASSISTANT_OWNERSHIP
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.persistence.user_store import build_user_assistant_store

log = structlog.get_logger(__name__)

# 历史本地开发 token；公开值，只可能出现在 dev_mode=True 的单用户环境。
_PUBLIC_DEV_TOKEN = "lca-local"  # noqa: S105 — documented dev value, never an accepted production secret


class Config(BaseModel):
    """ownership 插件配置。"""

    model_config = ConfigDict(extra="forbid")

    database_url: str | None = None
    """``{from_env: LCA_DATABASE_URL}`` 展开值；``None``/空 = SQLite。"""

    dev_mode: bool = False
    """True = 归属检查放行（存量单用户行为）；False = fail-closed。"""

    expected_token: SecretStr | str | None = None
    """``LCA_AUTH_EXPECTED_TOKEN`` 展开值；``None`` = 未配置。

    没有公开默认值：``dev_mode=False`` 且为空时 setup fail-loud。
    """

    @field_validator("dev_mode", mode="before")
    @classmethod
    def _coerce_dev_mode(cls, v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)


def _secret_value(value: SecretStr | str | None) -> str:
    """展开 ``SecretStr`` / ``str``，两侧去空白；``None`` 视为未配置。"""
    if value is None:
        return ""
    if isinstance(value, SecretStr):
        return value.get_secret_value().strip()
    return str(value).strip()


@plugin(
    id="lca.plugins.assistant.ownership",
    provides=(ASSISTANT_OWNERSHIP.key,),
    requires=("web_server",),
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "用户↔助理归属关系（ADR-0252 D2/D3）：LCA 自有数据库控制，"
        "安装 app.state.assistant_ownership 供路由/run 归属隔离。"
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G9_INTERACTION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca.plugins.assistant.ownership.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("web_server",),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """构造 store，提供 capability，并安装到 ``app.state.assistant_ownership``。"""
    store = build_user_assistant_store(database_url=config.database_url or "")
    ctx.provide(ASSISTANT_OWNERSHIP.key, store)

    expected_token = _secret_value(config.expected_token)
    if not config.dev_mode and not expected_token:
        raise RuntimeError(
            "assistant.ownership: expected_token is empty while dev_mode=False. "
            "Set LCA_AUTH_EXPECTED_TOKEN and inject it via "
            "`expected_token: {from_env: LCA_AUTH_EXPECTED_TOKEN}`. "
            "Refusing to boot with an implicit/public bearer token."
        )
    if not config.dev_mode and expected_token == _PUBLIC_DEV_TOKEN:
        raise RuntimeError(
            "assistant.ownership: expected_token equals the public dev value "
            f"{_PUBLIC_DEV_TOKEN!r} while dev_mode=False. "
            "Use a deployment-specific LCA_AUTH_EXPECTED_TOKEN, or set "
            "LCA_DEV_MODE=true for single-user development."
        )

    handle = ctx.require("web_server")
    app = getattr(handle, "app", None)
    if app is not None and hasattr(app, "state"):
        app.state.assistant_ownership = store
        app.state.lca_auth_expected_token = expected_token
        app.state.lca_auth_dev_mode = config.dev_mode
    log.info("assistant.ownership.installed", dev_mode=config.dev_mode)


__all__ = ["Config", "setup"]
