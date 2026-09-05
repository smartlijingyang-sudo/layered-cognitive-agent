"""session.title.v1 词表注册回归锁(ADR-0188,C11 四件套之测试端)。"""

from __future__ import annotations

import dataclasses
import json

import pytest

from lca.contracts.harness.memory.events import SessionTitle
from lca.contracts.harness.tasks.session import event_registry, event_type_of


def test_session_title_registered_in_registry() -> None:
    registry = event_registry()
    assert registry["session.title.v1"] is SessionTitle


def test_session_title_event_type_and_visibility() -> None:
    assert SessionTitle._event_type == "session.title.v1"
    # 标题事件 log-only:绝不进模型可见面(非 "model" 档)
    assert SessionTitle._visibility == "audit"


def test_session_title_is_frozen_dataclass() -> None:
    title = SessionTitle(title="t", message_seqs=(1,), source="fallback")
    assert dataclasses.is_dataclass(title)
    with pytest.raises(dataclasses.FrozenInstanceError):
        title.title = "other"  # type: ignore[misc]


def test_session_title_json_serializable() -> None:
    title = SessionTitle(title="你好 world", message_seqs=(0, 3), source="provider")
    encoded = json.dumps(dataclasses.asdict(title), allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded == {"title": "你好 world", "message_seqs": [0, 3], "source": "provider"}


def test_session_title_accepts_user_rename_shape() -> None:
    """用户重命名形态:空 message_seqs + source='user'。"""
    title = SessionTitle(title="renamed", message_seqs=(), source="user")
    assert title.message_seqs == ()
    assert title.source == "user"


def test_event_type_of_resolves_session_title() -> None:
    title = SessionTitle(title="t", message_seqs=(), source="fallback")
    assert event_type_of(title) == "session.title.v1"
