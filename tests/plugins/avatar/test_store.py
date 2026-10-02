import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from lca.contracts.models.avatar import (
    CANDIDATE_TTL,  # noqa: F401  # 同上
    AvatarState,
    AvatarVariant,  # noqa: F401  # 后续任务消费该类型，此处保持公共导入面
)
from lca.plugins.avatar.store import AvatarStore


@pytest.fixture()
def store(tmp_path: Path) -> AvatarStore:
    return AvatarStore(tmp_path / "avatar")


def _state(assistant_id: str = "asst_1") -> AvatarState:
    return AvatarState(
        assistant_id=assistant_id,
        active=None,
        candidates=[],
        updated_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


def test_save_and_load_state(store: AvatarStore):
    store.save_state(_state())
    loaded = store.load_state("asst_1")
    assert loaded.assistant_id == "asst_1"
    assert loaded.active is None


def test_write_and_read_image(store: AvatarStore, tmp_path: Path):
    buf = io.BytesIO()
    Image.new("RGB", (512, 512), (0, 128, 255)).save(buf, "PNG")
    variant = store.write_image("asst_1", "c1", "original", buf.getvalue())
    assert variant.size == "original"
    assert variant.width == 512 and variant.height == 512
    stored = store.read_image("asst_1", "c1", "original")
    with Image.open(io.BytesIO(stored)) as im:
        assert im.format == "PNG"
        assert im.size == (512, 512)
    assert (tmp_path / "avatar" / "candidates" / "c1" / "original.png").exists()


def test_write_image_original_normalizes_jpeg_to_png(store: AvatarStore):
    """JPEG 输入落盘 original 时必须重编码为真实 PNG 并记录实际尺寸。"""
    buf = io.BytesIO()
    Image.new("RGB", (320, 200), (10, 20, 30)).save(buf, "JPEG")
    variant = store.write_image("asst_1", "c1", "original", buf.getvalue())
    assert variant.size == "original"
    assert variant.width == 320 and variant.height == 200
    path = store.candidate_dir("c1") / "original.png"
    assert path.exists()
    with Image.open(path) as im:
        assert im.format == "PNG"
        assert im.size == (320, 200)


def test_write_image_small_normalizes_jpeg_to_png(store: AvatarStore):
    """JPEG 输入落盘 small 时同样重编码为 PNG（内容类型恒为 PNG）。"""
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (200, 100, 50)).save(buf, "JPEG")
    variant = store.write_image("asst_1", "c1", "small", buf.getvalue())
    assert variant.size == "small"
    assert variant.width == 128 and variant.height == 96
    path = store.candidate_dir("c1") / "small.png"
    assert path.exists()
    with Image.open(path) as im:
        assert im.format == "PNG"
        assert im.size == (128, 96)


def test_write_image_resizes_small(store: AvatarStore):
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (255, 0, 0)).save(buf, "PNG")
    variant = store.write_image("asst_1", "c1", "small", buf.getvalue())
    assert variant.size == "small"
    assert variant.width == 64 and variant.height == 64
    path = store.candidate_dir("c1") / "small.png"
    assert path.exists()
    with Image.open(path) as im:
        assert im.format == "PNG"
        assert im.size == (64, 64)


def test_write_video(store: AvatarStore):
    rel = store.write_video("asst_1", "c1", b"mp4-bytes")
    assert rel == "video/c1.mp4"
    assert (store.base_dir / "video" / "c1.mp4").read_bytes() == b"mp4-bytes"


def test_copy_candidate_to_active(store: AvatarStore):
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    cand = store._make_candidate("asst_1", "c1", "create", "prompt", now)
    store.save_state(
        AvatarState(assistant_id="asst_1", active=None, candidates=[cand], updated_at=now)
    )
    bundle = store.copy_candidate_to_active("asst_1", cand)
    assert bundle.candidate_id == "c1"
    assert (store.active_dir() / "c1" / "original.png").exists()


def test_cleanup_expired(store: AvatarStore):
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    expired = store._make_candidate("asst_1", "old", "create", "p", now - timedelta(hours=25))
    store.save_state(
        AvatarState(assistant_id="asst_1", active=None, candidates=[expired], updated_at=now)
    )
    removed = store.cleanup_expired(now)
    assert removed == 1
    assert store.load_state("asst_1").candidates == []
