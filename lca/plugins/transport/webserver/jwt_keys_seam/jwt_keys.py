"""JWT keys seam — Profile-injected private/public PEM pair for the webserver WS handshake.

ADR: see ``docs/notes/jwt-secret-injection-via-profile.md`` (proposed).

Context
-------
``lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth`` historically
read ``LCA_JWT_SECRET`` / ``LCA_JWT_PUBLIC_KEY`` directly via ``os.environ``. That path
violates AGENTS §4 ("插件不得自行读取 os.environ;密钥只能经 Profile {from_env: ...} 进入")
and was the root cause of ``POST /lca-api/runs → 500 InvalidTokenError("LCA_JWT_SECRET not set")``
when the kernel PID was started without that env var.

This seam:

- Resolves the private/public PEM from Profile config, which the harness resolves
  via ``{from_env: LCA_JWT_SECRET}`` style refs (see ``lca/harness/profile/plan/declarations.py``
  ``expand_env_refs``). Plugin code never touches ``os.environ``.
- Falls back to dev-mode: when ``jwt.dev_mode: true`` is configured and neither
  ``jwt.private_pem`` nor ``jwt.public_pem`` is set, a fresh RS256 keypair is
  generated in-process. Dev keys are valid only within the lifetime of a single
  kernel process; multi-replica deployments must disable dev-mode and inject
  stable PEM material via ``from_env``.
- Provides the resolved key pair as the ``jwt_keys`` capability so the
  webserver bootstrap can install it on ``app.state.jwt_keys`` and so the
  command-endpoint handlers can pass ``private_key_pem`` to ``mint_user_jwt``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    RSAPublicKey,
)
from pydantic import BaseModel, Field

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
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


class JwtConfig(BaseModel):
    """Profile schema accepted by ``lca-webserver-jwt-keys``.

    Three resolution paths (first non-empty wins):

    1. ``private_pem`` / ``public_pem``: literal PEM string or
       ``{from_env: NAME}`` reference (resolved by the harness).
    2. ``dev_mode: true``: when at least ``private_pem`` is missing, a fresh
       RS256 keypair is generated. ``public_pem`` is derived from the
       generated private key.
    3. Both ``private_pem`` and ``public_pem`` are missing and
       ``dev_mode`` is not true → plugin setup raises ``RuntimeError``.
    """

    model_config = {"extra": "forbid"}

    private_pem: str | None = Field(
        default=None,
        description=(
            "PEM-encoded PKCS8 RSA private key, or {from_env: NAME} reference. "
            "Required unless dev_mode is true."
        ),
    )
    public_pem: str | None = Field(
        default=None,
        description=(
            "PEM-encoded SPKI RSA public key, or {from_env: NAME} reference. "
            "Optional when private_pem is set (derived from the private key). "
            "Required only when dev_mode is true and no private_pem is given."
        ),
    )
    dev_mode: bool = Field(
        default=False,
        description=(
            "Generate a fresh RS256 keypair at plugin setup. Dev-only — the keypair "
            "changes on every kernel restart. Must be false for multi-replica deployments."
        ),
    )


@dataclass(frozen=True, slots=True)
class JwtKeys:
    """Resolved keypair handed to webserver handlers via ``app.state.jwt_keys``."""

    private_pem: str
    public_pem: str
    algorithm: Literal["RS256"] = "RS256"


def _ensure_private(pem: str) -> RSAPrivateKey:
    try:
        key = serialization.load_pem_private_key(pem.encode(), password=None)
    except ValueError as exc:
        raise RuntimeError(
            f"jwt.private_pem is not a valid PEM-encoded PKCS8 private key: {exc}"
        ) from exc
    if not isinstance(key, RSAPrivateKey):
        raise RuntimeError("jwt.private_pem must be an RSA private key")
    return key


def _derive_public_pem(private_pem: str) -> str:
    private = _ensure_private(private_pem)
    public = private.public_key()
    if not isinstance(public, RSAPublicKey):
        raise RuntimeError("derived public key is not RSA")
    return (
        public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
        .strip()
    )


def _generate_dev_keypair() -> tuple[str, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = (
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode()
        .strip()
    )
    public_pem = _derive_public_pem(private_pem)
    return private_pem, public_pem


@plugin(
    id="lca-webserver-jwt-keys",
    provides=("jwt_keys",),
    requires=(),
    layer="L0",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Resolve JWT signing keys from Profile config (or generate dev-mode keypair) "
        "and provide them as the `jwt_keys` capability."
    ),
    test_suite="tests.lca_plugins.transport.webserver.jwt_keys_seam.test_jwt_keys_seam",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.bootstrap",)),
        observability=EvidenceContract(
            descriptors=("lca-webserver-jwt-keys.resolved",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("jwt.config",),
        emits=("jwt_keys.resolved",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: JwtConfig) -> None:
    private_pem = (config.private_pem or "").strip() or None
    public_pem = (config.public_pem or "").strip() or None

    if private_pem is None and config.dev_mode:
        private_pem, public_pem = _generate_dev_keypair()
    elif private_pem is not None and public_pem is None:
        public_pem = _derive_public_pem(private_pem)

    if private_pem is None or public_pem is None:
        raise RuntimeError(
            "lca-webserver-jwt-keys: JWT keys are not configured. Provide "
            "`jwt.private_pem` (with optional `jwt.public_pem`) via Profile, "
            "or set `jwt.dev_mode: true` for local development."
        )

    # Validate PEM shape eagerly so a typo fails fast at boot rather than at first request.
    _ensure_private(private_pem)
    keys = JwtKeys(private_pem=private_pem, public_pem=public_pem)
    ctx.provide("jwt_keys", keys)


__all__ = [
    "JwtConfig",
    "JwtKeys",
    "derive_public_pem",
    "generate_dev_keypair",
]


# Public re-exports so tests can exercise the helpers without importing private names.
derive_public_pem = _derive_public_pem
generate_dev_keypair = _generate_dev_keypair
