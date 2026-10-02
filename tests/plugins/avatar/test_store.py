import io
import json
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


def test_load_state_prunes_expired_candidates(store: AvatarStore):
    """惰性清理：读状态时过期候选消失，未过期候选保留。"""
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    expired = store._make_candidate("asst_1", "old", "create", "p", now - timedelta(hours=25))
    fresh = store._make_candidate("asst_1", "new", "create", "p", now)
    store.save_state(
        AvatarState(
            assistant_id="asst_1",
            active=None,
            candidates=[expired, fresh],
            updated_at=now,
        )
    )
    loaded = store.load_state("asst_1")
    assert [c.candidate_id for c in loaded.candidates] == ["new"]
    # 目录清理由 ``cleanup_expired``（调度器小时扫除）负责，load_state 只剪状态。


def test_save_state_appends_revision(store: AvatarStore, tmp_path: Path):
    """每次状态写入都向 assistant home ``revisions/avatar-N.json`` 追加快照。"""
    store.save_state(_state())
    revisions_dir = tmp_path / "revisions"
    assert (revisions_dir / "avatar-0.json").exists()
    store.save_state(_state())
    assert (revisions_dir / "avatar-1.json").exists()
    snapshot = json.loads((revisions_dir / "avatar-1.json").read_text(encoding="utf-8"))
    assert snapshot["kind"] == "avatar"
    assert snapshot["assistant_id"] == "asst_1"


def test_multi_assistant_store_isolation(tmp_path: Path):
    """spec §5：不同助理的 store 互不可见；B 的 set 不得清空 A 的 active。"""
    from types import SimpleNamespace

    from lca.plugins.avatar.registry import avatar_service_registry
    from lca.plugins.avatar.store import resolve_safe_path

    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    store_a = AvatarStore(tmp_path / "asst_a" / "avatar")
    store_b = AvatarStore(tmp_path / "asst_b" / "avatar")
    avatar_service_registry.clear()
    try:
        avatar_service_registry.register("asst_a", SimpleNamespace(store=store_a))
        avatar_service_registry.register("asst_b", SimpleNamespace(store=store_b))

        cand_a = store_a._make_candidate("asst_a", "a1", "create", "p", now)
        store_a.save_state(
            AvatarState(assistant_id="asst_a", active=None, candidates=[cand_a], updated_at=now)
        )
        cand_b = store_b._make_candidate("asst_b", "b1", "create", "p", now)
        store_b.save_state(
            AvatarState(assistant_id="asst_b", active=None, candidates=[cand_b], updated_at=now)
        )

        store_a.copy_candidate_to_active("asst_a", cand_a)
        store_b.copy_candidate_to_active("asst_b", cand_b)

        # B 的 set 不得清空 A 的 active 文件。
        assert (store_a.active_dir() / "a1" / "original.png").exists()
        assert (store_b.active_dir() / "b1" / "original.png").exists()

        # A 的 active URL 仍可服务；B 读不到 A 的文件。
        assert resolve_safe_path("asst_a", "active/a1/original.png") != b""
        with pytest.raises(FileNotFoundError):
            resolve_safe_path("asst_b", "active/a1/original.png")
    finally:
        avatar_service_registry.clear()
