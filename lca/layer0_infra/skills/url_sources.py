"""URL classification for skill import sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

_LOBEHUB_SKILL_MD_RE = re.compile(
    r"^https?://(?:www\.)?lobehub\.com/skills/([^/]+)/skill\.md/?$",
    re.IGNORECASE,
)
_LOBEHUB_SKILL_PAGE_RE = re.compile(
    r"^https?://(?:www\.)?(?:market\.)?lobehub\.com/s/skills/([^/]+)/?$",
    re.IGNORECASE,
)
_GITHUB_TREE_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/tree/([^/]+)(?:/(.*))?$",
    re.IGNORECASE,
)
_GITHUB_BLOB_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/blob/([^/]+)(?:/(.*))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedSkillUrl:
    kind: str
    url: str
    market_identifier: str = ""
    owner: str = ""
    repo: str = ""
    ref: str = ""
    path: str = ""


def parse_skill_url(url: str, *, kind: str = "auto") -> ParsedSkillUrl:
    text = url.strip()
    if not text:
        raise ValueError("url 不能为空")

    match = _LOBEHUB_SKILL_MD_RE.match(text)
    if match:
        return ParsedSkillUrl(
            kind="market",
            url=text,
            market_identifier=match.group(1),
        )

    match = _LOBEHUB_SKILL_PAGE_RE.match(text)
    if match:
        return ParsedSkillUrl(
            kind="market",
            url=text,
            market_identifier=match.group(1),
        )

    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    path_lower = (parsed.path or "").lower()

    if kind == "zip" or path_lower.endswith(".zip"):
        return ParsedSkillUrl(kind="zip", url=text)

    if host in {"raw.githubusercontent.com"}:
        return ParsedSkillUrl(kind="raw", url=text)

    match = _GITHUB_TREE_RE.match(text)
    if match:
        return ParsedSkillUrl(
            kind="github_dir",
            url=text,
            owner=match.group(1),
            repo=match.group(2),
            ref=match.group(3),
            path=(match.group(4) or "").strip("/"),
        )

    match = _GITHUB_BLOB_RE.match(text)
    if match:
        blob_path = (match.group(4) or "").strip("/")
        return ParsedSkillUrl(
            kind="github_file",
            url=text,
            owner=match.group(1),
            repo=match.group(2),
            ref=match.group(3),
            path=blob_path,
        )

    if path_lower.endswith(".md") or kind == "url":
        return ParsedSkillUrl(kind="markdown", url=text)

    if host.endswith("github.com"):
        return ParsedSkillUrl(kind="github_repo", url=text)

    return ParsedSkillUrl(kind="url", url=text)


def github_raw_url(owner: str, repo: str, ref: str, path: str) -> str:
    clean = path.strip("/")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{clean}"


def is_host_allowed(url: str, allowed_hosts: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    allowed = {h.lower() for h in allowed_hosts}
    return host in allowed or any(host.endswith(f".{h}") for h in allowed if h)
