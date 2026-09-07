"""Shared fixtures for L2 in-process node contract tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def rsa_keys() -> dict[str, str]:
    """Generate an ephemeral RSA keypair so JWT mint/verify works.

    The keypair lives only for the pytest session; tests that mint a
    token pass it via ``private_key_pem=rsa_keys["private"]`` so we
    never write to the real LCA_JWT_SECRET env.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    os.environ["LCA_JWT_SECRET"] = private_pem
    os.environ["LCA_JWT_PUBLIC_KEY"] = public_pem
    os.environ["LCA_REDIS_URL"] = os.environ.get(
        "LCA_REDIS_URL", "redis://127.0.0.1:6379/0"
    )
    return {"private": private_pem, "public": public_pem}


@pytest.fixture
def lca_gateway_app(rsa_keys):  # noqa: ARG001
    """Build the LcaAgentGateway Starlette app with no injected RunPort."""
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.agent_gateway import (
        build_agent_gateway_app,
    )

    return build_agent_gateway_app()