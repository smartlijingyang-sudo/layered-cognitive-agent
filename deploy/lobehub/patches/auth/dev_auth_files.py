"""Patch: dev_auth_files — Create LocalDevAuth component files."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

_LOCAL_DEV_NO_AUTH_TS = """\
/** LCA local stack: skip Better Auth session polling (no login, no get-session). */
export const isLocalDevNoAuth = (): boolean => {
  const flag = process.env.NEXT_PUBLIC_ENABLE_MOCK_DEV_USER;
  return flag === '1' || flag === 'true';
};

export const getLocalDevUserId = (): string =>
  process.env.NEXT_PUBLIC_MOCK_DEV_USER_ID ||
  process.env.MOCK_DEV_USER_ID ||
  'local-dev-user';
"""

_LOCAL_DEV_USER_UPDATER_TSX = """\
'use client';

import { memo, useLayoutEffect } from 'react';

import { getLocalDevUserId } from '@/layout/AuthProvider/localDevNoAuth';
import { useUserStore } from '@/store/user';
import { type LobeUser } from '@/types/user';

/**
 * Static local user — replaces Better Auth `useSession()` polling.
 * Server APIs already trust `ENABLE_MOCK_DEV_USER` (see trpc lambda context).
 */
const LocalDevUserUpdater = memo(() => {
  useLayoutEffect(() => {
    const userId = getLocalDevUserId();
    const user: LobeUser = {
      avatar: '',
      email: 'dev@localhost',
      fullName: 'Local Dev',
      id: userId,
      username: 'local',
    };

    useUserStore.setState({
      isLoaded: true,
      isSignedIn: true,
      user,
    });
  }, []);

  return null;
});

LocalDevUserUpdater.displayName = 'LocalDevUserUpdater';

export default LocalDevUserUpdater;
"""

_LOCAL_DEV_AUTH_INDEX_TSX = """\
import { type PropsWithChildren } from 'react';

import LocalDevUserUpdater from './LocalDevUserUpdater';

/** LCA: no login UI, no `/api/auth/get-session` polling. */
const LocalDevAuth = ({ children }: PropsWithChildren) => {
  return (
    <>
      {children}
      <LocalDevUserUpdater />
    </>
  );
};

export default LocalDevAuth;
"""

meta = PatchMeta(
    name="dev_auth_files",
    description="Create LocalDevAuth component files",
    files=(
        "src/layout/AuthProvider/localDevNoAuth.ts",
        "src/layout/AuthProvider/LocalDevAuth/LocalDevUserUpdater.tsx",
        "src/layout/AuthProvider/LocalDevAuth/index.tsx",
    ),
    risk="low",
    category="auth",
    depends_on=(),
    why="Local dev needs no-auth mode; Better Auth requires HTTPS + OAuth",
    technical_detail=(
        "Create 3 new files: localDevNoAuth.ts (flag check), "
        "LocalDevAuth/index.tsx (wrapper), LocalDevUserUpdater.tsx (injects static user)."
    ),
    verify_file="src/layout/AuthProvider/localDevNoAuth.ts",
    verify_marker="isLocalDevNoAuth",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    if ctx.has_marker("src/layout/AuthProvider/localDevNoAuth.ts", "isLocalDevNoAuth"):
        return False
    files = {
        "src/layout/AuthProvider/localDevNoAuth.ts": _LOCAL_DEV_NO_AUTH_TS,
        "src/layout/AuthProvider/LocalDevAuth/LocalDevUserUpdater.tsx": _LOCAL_DEV_USER_UPDATER_TSX,
        "src/layout/AuthProvider/LocalDevAuth/index.tsx": _LOCAL_DEV_AUTH_INDEX_TSX,
    }
    for rel, content in files.items():
        ctx.create_file(rel, content)
    return True
