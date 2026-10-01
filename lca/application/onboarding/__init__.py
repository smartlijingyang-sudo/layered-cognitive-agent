"""Onboarding application layer package."""

from lca.application.onboarding.script import (
    extract_user_name_from_user_md,
    get_onboarding_opening_messages,
)

__all__ = [
    "extract_user_name_from_user_md",
    "get_onboarding_opening_messages",
]
