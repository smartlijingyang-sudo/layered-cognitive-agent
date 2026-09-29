"""Tests for lca_user_header frontend middleware patch."""

from __future__ import annotations

from deploy.lobehub.engine import discover_patches
from deploy.lobehub.patches.auth.lca_user_header import apply, meta

_STUB_DEFINE_CONFIG = """import { type NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

export const createProxyConfig = () => {
  const betterAuthMiddleware = async (req: NextRequest) => {
    logBetterAuth('Route protection status: %s, %s', req.url, isProtected ? 'protected' : 'public');

    // Skip session lookup for public routes to reduce latency
    if (!isProtected) return response;

    const mockDevFlag = process.env.ENABLE_MOCK_DEV_USER;
    if (mockDevFlag === '1' || mockDevFlag === 'true') {
      logBetterAuth('ENABLE_MOCK_DEV_USER: skipping session gate');
      return response;
    }

    if (!isLoggedIn) {
      logBetterAuth('Request a free route but not login, allow visit without auth header');
    }

    return response;
  };
};
"""


class _MockContext:
    def __init__(self, initial_text: str) -> None:
        self.files = {"src/libs/next/proxy/define-config.ts": initial_text}

    def read(self, rel: str) -> str:
        if rel not in self.files:
            raise FileNotFoundError(f"File not found: {rel}")
        return self.files[rel]

    def write(self, rel: str, text: str) -> None:
        self.files[rel] = text

    def has_marker(self, rel: str, marker: str) -> bool:
        return marker in self.files.get(rel, "")


def test_lca_user_header_patch_meta() -> None:
    assert meta.name == "lca_user_header"
    assert meta.category == "auth"
    assert "src/libs/next/proxy/define-config.ts" in meta.files
    assert "LCA x-lca-user-id" in meta.verify_marker


def test_lca_user_header_patch_apply_and_idempotence() -> None:
    ctx = _MockContext(_STUB_DEFINE_CONFIG)

    applied = apply(ctx)  # type: ignore[arg-type]
    assert applied is True
    content = ctx.read("src/libs/next/proxy/define-config.ts")

    assert "x-lca-user-id" in content
    assert "authorization" in content
    assert "Bearer" in content

    # Second apply: idempotent
    applied_again = apply(ctx)  # type: ignore[arg-type]
    assert applied_again is False


def test_lca_user_header_patch_discovered() -> None:
    all_patches = discover_patches()
    assert any(pm.meta.name == "lca_user_header" for pm in all_patches)
