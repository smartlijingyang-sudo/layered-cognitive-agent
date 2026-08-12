"""Patch: dev_auth_vite — Swap BetterAuth for LocalDevAuth in Vite mode."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="dev_auth_vite",
    description="Swap BetterAuth for LocalDevAuth in Vite mode",
    files=("src/layout/AuthProvider/index.vite.tsx",),
    risk="medium",
    category="auth",
    depends_on=("dev_auth_files",),
    why="Vite SPA mode needs the auth provider swap",
    technical_detail="When ENABLE_MOCK_DEV_USER is set, render LocalDevAuth instead of BetterAuth.",
    verify_file="src/layout/AuthProvider/index.vite.tsx",
    verify_marker="LocalDevAuth",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    rel = "src/layout/AuthProvider/index.vite.tsx"
    text = ctx.read(rel)
    if "LocalDevAuth" in text and "isLocalDevNoAuth" in text:
        return False
    old = """import BetterAuth from './BetterAuth';
import Desktop from './Desktop';

const AuthProvider = ({ children }: PropsWithChildren) => {
  if (isDesktop) {
    return <Desktop>{children}</Desktop>;
  }

  // In SPA/Vite mode, always use BetterAuth.
  // If auth is not configured on the server, useSession() will return no session
  // and the user will be treated as not signed in — same effect as NoAuth.
  return <BetterAuth>{children}</BetterAuth>;
};"""
    new = """import BetterAuth from './BetterAuth';
import Desktop from './Desktop';
import LocalDevAuth from './LocalDevAuth';
import { isLocalDevNoAuth } from './localDevNoAuth';

const AuthProvider = ({ children }: PropsWithChildren) => {
  if (isDesktop) {
    return <Desktop>{children}</Desktop>;
  }

  // LCA local stack: static dev user, no Better Auth session polling.
  if (isLocalDevNoAuth()) {
    return <LocalDevAuth>{children}</LocalDevAuth>;
  }

  return <BetterAuth>{children}</BetterAuth>;
};"""
    if old not in text:
        if "LocalDevAuth" in text:
            return False
        raise SystemExit("[dev_auth_vite] AuthProvider anchor not found")
    ctx.write(rel, text.replace(old, new, 1))
    return True
