"""Tests for signup_username frontend patch."""

from __future__ import annotations

from deploy.lobehub.engine import discover_patches
from deploy.lobehub.patches.auth.signup_username import apply, meta

_STUB_USE_SIGN_UP = """import { Form } from 'antd';
import { useState } from 'react';

export const useSignUp = () => {
  const handleSignUp = async (values: SignUpFormValues) => {
    try {
      const callbackUrl = searchParams.get('callbackUrl') || '/';
      const redirectUrl = buildOnboardingRedirectUrl(callbackUrl);
      const username = values.email.split('@')[0];
      const fetchOptions = await getFetchOptions();

      const submit = async (nextFetchOptions?: AuthFetchOptions) =>
        signUp.email({
          callbackURL: redirectUrl,
          email: values.email,
          fetchOptions: nextFetchOptions,
          name: username,
          password: values.password,
        });

      let { error } = await submit(fetchOptions);
    } catch {}
  };
};
"""


class _MockContext:
    def __init__(self, initial_text: str) -> None:
        self.files = {"src/features/Auth/SignUp/useSignUp.ts": initial_text}

    def read(self, rel: str) -> str:
        if rel not in self.files:
            raise FileNotFoundError(f"File not found: {rel}")
        return self.files[rel]

    def write(self, rel: str, text: str) -> None:
        self.files[rel] = text

    def has_marker(self, rel: str, marker: str) -> bool:
        return marker in self.files.get(rel, "")


def test_signup_username_patch_meta() -> None:
    assert meta.name == "signup_username"
    assert meta.category == "auth"
    assert "src/features/Auth/SignUp/useSignUp.ts" in meta.files
    assert meta.verify_marker == "/* LCA: persist username for Better Auth resolve-username lookup */"


def test_signup_username_patch_apply_and_idempotence() -> None:
    ctx = _MockContext(_STUB_USE_SIGN_UP)

    # First apply: returns True and updates content
    applied = apply(ctx)  # type: ignore[arg-type]
    assert applied is True
    content = ctx.read("src/features/Auth/SignUp/useSignUp.ts")

    assert "/* LCA: persist username for Better Auth resolve-username lookup */" in content
    assert "username," in content
    assert "name: username" in content

    # Second apply: idempotent, returns False
    applied_again = apply(ctx)  # type: ignore[arg-type]
    assert applied_again is False


def test_signup_username_patch_discovered() -> None:
    all_patches = discover_patches()
    assert any(pm.meta.name == "signup_username" for pm in all_patches)
