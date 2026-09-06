"""Attachment identity settings — YAML policy is SSOT, env can override knobs."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AttachmentPolicyDocument(BaseModel):
    """Validated policy file. Prompt markers, inbox layout, inline rules."""

    model_config = {"frozen": True}

    system_context_open: str
    system_context_close: str
    system_context_open_prefix: str
    inbox_dir: str
    inline_max_bytes: int = Field(ge=0)
    inline_mime_prefixes: tuple[str, ...]
    inline_name_suffixes: tuple[str, ...]
    files_instruction: str
    machine_policy: str
    machine_uploaded_files_list_header: str
    sandbox_policy: str
    sandbox_uploaded_files_list_header: str

    @field_validator("inline_mime_prefixes", "inline_name_suffixes", mode="before")
    @classmethod
    def _tupleize(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(str(item) for item in value)
        return value

    def allows_inline(self, mime_type: str, name: str) -> bool:
        mime = mime_type.lower()
        lowered = name.lower()
        if any(mime.startswith(prefix.lower()) for prefix in self.inline_mime_prefixes):
            return True
        return any(lowered.endswith(suffix.lower()) for suffix in self.inline_name_suffixes)

    def machine_policy_text(self) -> str:
        return self.machine_policy.strip()

    def sandbox_policy_text(self, workspace_root: str) -> str:
        return self.sandbox_policy.format(workspace_root=workspace_root).strip()


def load_attachment_policy() -> AttachmentPolicyDocument:
    raw = yaml.safe_load(
        resources.files("lca.infrastructure.attachment")
        .joinpath("policy.yaml")
        .read_text(encoding="utf-8")
    )
    if not isinstance(raw, dict):
        raise ValueError("attachment policy.yaml must be a mapping")
    return AttachmentPolicyDocument.model_validate(raw)


class AttachmentSettings(BaseSettings):
    """Optional env overrides (``LCA_ATTACHMENT_*``) on top of policy.yaml."""

    model_config = SettingsConfigDict(
        env_prefix="LCA_ATTACHMENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    inbox_dir: str | None = None
    inline_max_bytes: int | None = Field(default=None, ge=0)

    def resolve(self) -> AttachmentPolicyDocument:
        base = load_attachment_policy()
        updates: dict[str, object] = {}
        if self.inbox_dir is not None and self.inbox_dir.strip():
            updates["inbox_dir"] = self.inbox_dir.strip()
        if self.inline_max_bytes is not None:
            updates["inline_max_bytes"] = self.inline_max_bytes
        if not updates:
            return base
        return base.model_copy(update=updates)


@lru_cache
def get_attachment_settings() -> AttachmentSettings:
    return AttachmentSettings()


def get_attachment_policy() -> AttachmentPolicyDocument:
    return get_attachment_settings().resolve()


def reset_attachment_settings_for_tests() -> None:
    get_attachment_settings.cache_clear()
