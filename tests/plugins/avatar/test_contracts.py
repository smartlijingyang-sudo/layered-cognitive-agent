from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from pydantic import ValidationError

from lca.contracts.models.avatar import (
    AVATAR_SIZES,
    CANDIDATE_TTL,
    AvatarActiveBundle,  # noqa: F401  # 后续任务消费该类型，此处保持公共导入面
    AvatarCandidate,
    AvatarState,
    AvatarUpdatedEvent,
    AvatarVariant,
)


def _variant(size: Literal["original", "small", "medium", "large"] = "original") -> AvatarVariant:
    return AvatarVariant(
        size=size,
        file_path=f"candidates/c1/{size}.png",
        url="/avatar/files/c1/original.png",
        width=512,
        height=512,
    )


def test_avatar_sizes_and_ttl():
    assert AVATAR_SIZES == ("original", "small", "medium", "large")
    assert timedelta(hours=24) == CANDIDATE_TTL


def test_candidate_expiry():
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    fresh = AvatarCandidate(
        candidate_id="c1",
        assistant_id="asst_1",
        kind="create",
        prompt="x",
        variants=(_variant(),),
        created_at=now - timedelta(hours=23),
        expires_at=now - timedelta(hours=23) + CANDIDATE_TTL,
    )
    assert fresh.is_expired(now) is False
    stale = fresh.model_copy(update={"expires_at": now - timedelta(seconds=1)})
    assert stale.is_expired(now) is True


def test_avatar_state_active_null_default():
    state = AvatarState(
        assistant_id="asst_1",
        active=None,
        candidates=[],
        updated_at=datetime(2026, 10, 2, tzinfo=UTC),
    )
    assert state.active is None
    assert state.candidates == []


def test_avatar_updated_event_types():
    ev = AvatarUpdatedEvent(
        type="avatar_updated", assistant_id="asst_1", payload={"candidate_id": "c1"}
    )
    assert ev.type == "avatar_updated"
    assert ev.payload["candidate_id"] == "c1"


def test_models_forbid_extra():
    with pytest.raises(ValidationError):
        AvatarVariant(size="original", file_path="x.png", url="u", width=1, height=1, extra_field=1)  # type: ignore[call-arg]
