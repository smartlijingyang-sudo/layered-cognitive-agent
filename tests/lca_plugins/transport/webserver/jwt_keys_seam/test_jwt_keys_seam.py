"""Tests for the ``lca-webserver-jwt-keys`` plugin.

Covers:
- ``from_env`` resolution is performed by the harness before the plugin
  setup runs, so this module never touches ``os.environ`` itself.
- Dev-mode generates a valid RS256 keypair.
- Missing both ``private_pem`` and ``dev_mode`` raises at setup time,
  matching the boot-fast-fail expectation in AGENTS §4.
"""

from __future__ import annotations

import asyncio

import pytest

from lca.plugins.transport.webserver.jwt_keys_seam.jwt_keys import (
    JwtConfig,
    JwtKeys,
    derive_public_pem,
    generate_dev_keypair,
)
from lca.plugins.transport.webserver.jwt_keys_seam.jwt_keys import (
    setup as plugin_setup,
)


class _FakeCtx:
    def __init__(self) -> None:
        self.provided: dict[str, object] = {}

    def provide(self, key: str, value: object) -> None:
        self.provided[key] = value


def test_generate_dev_keypair_produces_rsa_pem_pair() -> None:
    priv, pub = generate_dev_keypair()
    assert priv.startswith("-----BEGIN PRIVATE KEY-----")
    assert pub.startswith("-----BEGIN PUBLIC KEY-----")
    assert derive_public_pem(priv) == pub


def test_dev_mode_setup_provides_jwt_keys() -> None:
    ctx = _FakeCtx()
    asyncio.run(plugin_setup.setup(ctx, JwtConfig(dev_mode=True)))

    keys = ctx.provided["jwt_keys"]
    assert isinstance(keys, JwtKeys)
    assert keys.algorithm == "RS256"
    assert keys.private_pem.startswith("-----BEGIN PRIVATE KEY-----")
    assert keys.public_pem.startswith("-----BEGIN PUBLIC KEY-----")


def test_setup_with_only_private_pem_derives_public() -> None:
    priv, _pub = generate_dev_keypair()
    ctx = _FakeCtx()
    asyncio.run(plugin_setup.setup(ctx, JwtConfig(private_pem=priv)))

    keys = ctx.provided["jwt_keys"]
    assert isinstance(keys, JwtKeys)
    assert keys.private_pem == priv
    assert keys.public_pem.startswith("-----BEGIN PUBLIC KEY-----")


def test_setup_without_private_pem_and_without_dev_mode_raises() -> None:
    ctx = _FakeCtx()
    with pytest.raises(RuntimeError, match="JWT keys are not configured"):
        asyncio.run(plugin_setup.setup(ctx, JwtConfig()))


def test_setup_with_invalid_pem_raises() -> None:
    ctx = _FakeCtx()
    with pytest.raises(RuntimeError, match="not a valid PEM-encoded PKCS8"):
        asyncio.run(
            plugin_setup.setup(
                ctx,
                JwtConfig(
                    private_pem=("-----BEGIN PUBLIC KEY-----\nxxx\n-----END PUBLIC KEY-----")
                ),
            )
        )
