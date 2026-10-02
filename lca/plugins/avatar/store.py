"""Avatar 文件存储（ADR-0269 §2）。

state.json 是头像状态唯一真值；图片按候选/激活目录落盘。
"""

from __future__ import annotations

import io
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from PIL import Image

from lca.contracts.models.avatar import (
    AVATAR_SIZES,
    CANDIDATE_TTL,
    AvatarActiveBundle,
    AvatarCandidate,
    AvatarState,
    AvatarVariant,
    utcnow,
)

_STATE_FILE = "state.json"
_IMAGE_EXT = ".png"
_SIZES_PX: dict[str, tuple[int, int]] = {
    "small": (128, 128),
    "medium": (256, 256),
    "large": (512, 512),
}
_ORIGINAL_SIZE: tuple[int, int] = (512, 512)
# 1x1 透明 PNG，供 _make_candidate 落盘占位图片（测试没有真实生图字节）。
_PLACEHOLDER_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDATx\x9cc`\x00\x02\x00\x00\x05"
    b"\x00\x01z^\xab?\x00\x00\x00\x00IEND\xaeB`\x82"
)

AvatarSize = Literal["original", "small", "medium", "large"]


class AvatarStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def _state_path(self, assistant_id: str) -> Path:
        return self.base_dir / assistant_id / _STATE_FILE

    def load_state(self, assistant_id: str) -> AvatarState:
        path = self._state_path(assistant_id)
        if not path.exists():
            return AvatarState(
                assistant_id=assistant_id, active=None, candidates=[], updated_at=utcnow()
            )
        return AvatarState.model_validate_json(path.read_text(encoding="utf-8"))

    def save_state(self, state: AvatarState) -> None:
        path = self._state_path(state.assistant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)  # 原子写

    def candidate_dir(self, candidate_id: str) -> Path:
        return self.base_dir / "candidates" / candidate_id

    def active_dir(self) -> Path:
        return self.base_dir / "active"

    def _make_candidate(
        self,
        assistant_id: str,
        candidate_id: str,
        kind: Literal["create", "edit"],
        prompt: str,
        now: datetime,
    ) -> AvatarCandidate:
        """构造候选模型并落盘占位图片（测试辅助，生产由 write_image 落盘）。"""
        variants: list[AvatarVariant] = []
        variant_dir = self.candidate_dir(candidate_id)
        variant_dir.mkdir(parents=True, exist_ok=True)
        for raw_size in AVATAR_SIZES:
            size = cast("AvatarSize", raw_size)
            (variant_dir / f"{size}{_IMAGE_EXT}").write_bytes(_PLACEHOLDER_PNG)
            width, height = _ORIGINAL_SIZE if size == "original" else _SIZES_PX[size]
            variants.append(
                AvatarVariant(
                    size=size,
                    file_path=f"candidates/{candidate_id}/{size}{_IMAGE_EXT}",
                    url=f"/lca-api/v1/assistants/{assistant_id}/avatar/files/candidates/{candidate_id}/{size}{_IMAGE_EXT}",
                    width=width,
                    height=height,
                )
            )
        return AvatarCandidate(
            candidate_id=candidate_id,
            assistant_id=assistant_id,
            kind=kind,
            prompt=prompt,
            variants=tuple(variants),
            created_at=now,
            expires_at=now + CANDIDATE_TTL,
        )

    def write_image(
        self, assistant_id: str, candidate_id: str, size: AvatarSize, data: bytes
    ) -> AvatarVariant:
        rel_dir = f"candidates/{candidate_id}"
        target = self.base_dir / rel_dir / f"{size}{_IMAGE_EXT}"
        target.parent.mkdir(parents=True, exist_ok=True)
        # grok2api 代理返回 JPEG，但落盘扩展名/Content-Type 恒为 PNG；
        # 所有尺寸统一重编码为真实 PNG，避免 MIME 与实际字节不一致。
        if size == "original":
            width, height = _encode_original_png(data, target)
        else:
            width, height = _resize_image(data, target, _SIZES_PX[size])
        return AvatarVariant(
            size=size,
            file_path=f"{rel_dir}/{size}{_IMAGE_EXT}",
            url=f"/lca-api/v1/assistants/{assistant_id}/avatar/files/{rel_dir}/{size}{_IMAGE_EXT}",
            width=width,
            height=height,
        )

    def read_image(self, assistant_id: str, candidate_id: str, size: str) -> bytes:
        path = self.base_dir / f"candidates/{candidate_id}/{size}{_IMAGE_EXT}"
        if not path.exists():
            raise FileNotFoundError(path)
        return path.read_bytes()

    def write_video(self, assistant_id: str, candidate_id: str, data: bytes) -> str:
        """写视频变体到 ``avatar/video/<candidate_id>.mp4``，返回相对路径。"""
        rel_path = f"video/{candidate_id}.mp4"
        target = self.base_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return rel_path

    def copy_candidate_to_active(
        self, assistant_id: str, candidate: AvatarCandidate
    ) -> AvatarActiveBundle:
        active_root = self.active_dir()
        if active_root.exists():
            shutil.rmtree(active_root)
        active = active_root / candidate.candidate_id
        shutil.copytree(self.candidate_dir(candidate.candidate_id), active)
        variants = tuple(
            AvatarVariant(
                size=v.size,
                file_path=f"active/{candidate.candidate_id}/{v.size}{_IMAGE_EXT}",
                url=f"/lca-api/v1/assistants/{assistant_id}/avatar/files/active/{candidate.candidate_id}/{v.size}{_IMAGE_EXT}",
                width=v.width,
                height=v.height,
            )
            for v in candidate.variants
        )
        return AvatarActiveBundle(
            candidate_id=candidate.candidate_id,
            variants=variants,
            activated_at=utcnow(),
        )

    def cleanup_expired(self, now: datetime) -> int:
        removed = 0
        for path in self.base_dir.glob(f"*/{_STATE_FILE}"):
            state = AvatarState.model_validate_json(path.read_text(encoding="utf-8"))
            expired = [c for c in state.candidates if c.is_expired(now)]
            if not expired:
                continue
            for candidate in expired:
                shutil.rmtree(self.candidate_dir(candidate.candidate_id), ignore_errors=True)
            pruned = state.model_copy(
                update={"candidates": [c for c in state.candidates if not c.is_expired(now)]}
            )
            self.save_state(pruned)
            removed += len(expired)
        return removed


def _save_png_atomic(im: Image.Image, target: Path) -> None:
    """原子写 PNG：先写同目录临时文件再 replace，避免读图时看到半截字节。"""
    tmp = target.with_suffix(".tmp")
    im.save(tmp, "PNG")
    tmp.replace(target)


def _encode_original_png(data: bytes, target: Path) -> tuple[int, int]:
    """把原始字节重编码为真实 PNG（保持原尺寸），返回实际像素尺寸。"""
    with Image.open(io.BytesIO(data)) as im:
        rgb = im.convert("RGB")
        _save_png_atomic(rgb, target)
        return rgb.size


def _resize_image(data: bytes, target: Path, size: tuple[int, int]) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as im:
        rgb = im.convert("RGB")
        rgb.thumbnail(size, Image.Resampling.LANCZOS)
        _save_png_atomic(rgb, target)
        return rgb.size


# ADR-0269 §7：图片静态服务白名单 + 路径规范化。只允许三种根：
# candidates/<candidate_id>/<size>.png、active/<candidate_id>/<size>.png、
# video/<candidate_id>.mp4。candidate_id 由服务生成，形如
# ``create-20261002120000-0``（字母/数字/`-`/`_`）。
_AVATAR_FILE_WHITELIST = re.compile(
    r"^(?:"
    r"candidates/(?P<candidate_id>[A-Za-z0-9_-]+)/(?:original|small|medium|large)\.png"
    r"|active/(?P<active_id>[A-Za-z0-9_-]+)/(?:original|small|medium|large)\.png"
    r"|video/(?P<video_id>[A-Za-z0-9_-]+)\.mp4"
    r")$"
)


def resolve_safe_path(assistant_id: str, rel_path: str) -> bytes:
    """解析并读取 assistant 的 avatar 文件（白名单 + 路径归一化）。

    允许的根：``candidates/<candidate_id>/<size>.png``、
    ``active/<candidate_id>/<size>.png``、``video/<candidate_id>.mp4``。
    拒绝 ``..``、绝对路径、null 字节与任何越界路径（抛 ``ValueError``，
    REST 路由映射 400）；文件不存在抛 ``FileNotFoundError``（映射 404）。
    """
    from lca.plugins.avatar.registry import avatar_service_registry

    if "\x00" in rel_path:
        raise ValueError("avatar file path contains null byte")
    if rel_path.startswith("/") or "\\" in rel_path:
        raise ValueError("avatar file path must be relative")
    if _AVATAR_FILE_WHITELIST.match(rel_path) is None:
        raise ValueError(f"disallowed avatar file path: {rel_path!r}")

    normalized = Path(rel_path)
    if ".." in normalized.parts:
        raise ValueError("avatar file path traversal is not allowed")

    service = avatar_service_registry.get(assistant_id)
    base_dir = Path(service.store.base_dir)
    base_resolved = base_dir.resolve()
    target = (base_dir / rel_path).resolve()
    if not target.is_relative_to(base_resolved):
        raise ValueError("avatar file path escapes avatar base dir")
    if not target.is_file():
        raise FileNotFoundError(target)
    return target.read_bytes()


__all__ = ["AvatarStore", "resolve_safe_path"]
