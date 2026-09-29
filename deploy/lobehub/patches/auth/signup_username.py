"""Patch: signup_username — pass username to Better Auth signUp.email.

ADR-0252: Users registered via email/password need their username (derived
from email prefix) persisted to the database users.username column so that
the /api/auth/resolve-username endpoint can resolve username to email on sign-in.
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="signup_username",
    description="Pass username to Better Auth signUp.email so users.username is stored in DB",
    files=("src/features/Auth/SignUp/useSignUp.ts",),
    risk="low",
    category="auth",
    why="ADR-0252: enable username sign-in by populating users.username during registration",
    technical_detail=(
        "Better Auth schema has additionalFields.username, but useSignUp.ts "
        "only passed name: username and omitted username. This patch adds "
        "username to the signUp.email payload."
    ),
    verify_file="src/features/Auth/SignUp/useSignUp.ts",
    verify_marker="/* LCA: persist username for Better Auth resolve-username lookup */",
)


def apply(ctx: PatchContext) -> bool:
    rel = "src/features/Auth/SignUp/useSignUp.ts"
    if ctx.has_marker(rel, meta.verify_marker):
        return False

    text = ctx.read(rel)

    anchor = """      const submit = async (nextFetchOptions?: AuthFetchOptions) =>
        signUp.email({
          callbackURL: redirectUrl,
          email: values.email,
          fetchOptions: nextFetchOptions,
          name: username,
          password: values.password,
        });"""

    replacement = """      const submit = async (nextFetchOptions?: AuthFetchOptions) =>
        signUp.email({
          callbackURL: redirectUrl,
          email: values.email,
          fetchOptions: nextFetchOptions,
          name: username,
          password: values.password,
          /* LCA: persist username for Better Auth resolve-username lookup */
          username,
        } as any);"""

    if anchor not in text:
        raise AssertionError("signup_username: submit anchor not found in useSignUp.ts")

    text = text.replace(anchor, replacement, 1)
    ctx.write(rel, text)
    return True
