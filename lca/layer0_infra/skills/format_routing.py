"""Attachment format → operational skill routing (ADR-0048 / ADR-0051)."""

from __future__ import annotations

from typing import Any

# Extension / inspect profile type → skill_id candidates (installed via ADR-0048).
_FORMAT_SKILL_MAP: dict[str, tuple[str, ...]] = {
    "pdf": ("anthropics-skills-pdf",),
    "legacy_word": ("anthropics-skills-docx",),
    "docx": ("anthropics-skills-docx",),
    "pptx": ("anthropics-skills-pptx",),
    "xlsx": (),
    "excel": (),
    "csv": (),
}

_EXT_SKILL_MAP: dict[str, tuple[str, ...]] = {
    ".pdf": ("anthropics-skills-pdf",),
    ".doc": ("anthropics-skills-docx",),
    ".docx": ("anthropics-skills-docx",),
    ".pptx": ("anthropics-skills-pptx",),
    ".xlsx": (),
    ".xls": (),
    ".csv": (),
}


def skills_for_filename(name: str) -> tuple[str, ...]:
    lower = name.lower()
    for ext, skills in _EXT_SKILL_MAP.items():
        if lower.endswith(ext):
            return skills
    return ()


def skills_for_profile_entry(entry: dict[str, Any]) -> tuple[str, ...]:
    kind = str(entry.get("type") or "").lower()
    if kind in _FORMAT_SKILL_MAP:
        mapped = _FORMAT_SKILL_MAP[kind]
        if mapped:
            return mapped
    return ()


def enrich_inspect_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Attach suggested_skills to each file profile for prompt routing."""
    profiles = profile.get("profiles")
    if not isinstance(profiles, dict):
        return profile

    enriched: dict[str, Any] = dict(profiles)
    for name, raw in profiles.items():
        if not isinstance(raw, dict):
            continue
        entry = dict(raw)
        suggested = list(entry.get("suggested_skills") or [])
        if not suggested:
            suggested = list(skills_for_profile_entry(entry))
        if not suggested:
            suggested = list(skills_for_filename(str(name)))
        entry["suggested_skills"] = suggested
        enriched[name] = entry

    out = dict(profile)
    out["profiles"] = enriched
    return out


def suggested_skills_from_profile(profile: dict[str, Any] | None) -> tuple[str, ...]:
    """Flatten unique suggested skills from an inspect profile."""
    if not profile:
        return ()
    profiles = profile.get("profiles")
    if not isinstance(profiles, dict):
        return ()
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in profiles.values():
        if not isinstance(raw, dict):
            continue
        for skill_id in raw.get("suggested_skills") or []:
            sid = str(skill_id).strip()
            if sid and sid not in seen:
                seen.add(sid)
                ordered.append(sid)
    return tuple(ordered)


def format_suggested_skills_prompt(profile: dict[str, Any] | None) -> str:
    skills = suggested_skills_from_profile(profile)
    if not skills:
        return "（inspect 未匹配到 skill — 按 AVAILABLE_SKILLS 或 search_skill）"
    return "\n".join(f"- {sid}（附件格式匹配，优先 activate_skill）" for sid in skills)
