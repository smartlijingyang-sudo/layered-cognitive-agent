"""Tests for RoomRepository and RoomMessageRouter (ADR-0250)."""

from pathlib import Path

from lca.contracts.models.collaboration.peer import RoomSpec
from lca.domain.collaboration.room import (
    JsonRoomRepository,
    RoomMessageRouter,
)


def test_json_room_repository_lifecycle(tmp_path: Path):
    repo = JsonRoomRepository(base_dir=tmp_path)

    room = RoomSpec(
        room_id="room_arch_studio",
        display_name="李超架构工作室",
        coordinator_agent_id="coordinator_sam",
        member_peer_ids=("arch_guanlan", "arch_hengyue", "arch_jingchuan"),
        shared_topic_id="topic_arch_001",
        routing_policy="coordinator_first",
    )

    # 1. 初始为空
    assert repo.get("room_arch_studio") is None
    assert repo.list_rooms() == ()

    # 2. 保存并查询
    repo.save(room)
    fetched = repo.get("room_arch_studio")
    assert fetched == room
    assert len(repo.list_rooms()) == 1

    # 3. 删除
    assert repo.delete("room_arch_studio") is True
    assert repo.get("room_arch_studio") is None
    assert repo.delete("room_arch_studio") is False


def test_room_message_router_coordinator_first():
    room = RoomSpec(
        room_id="room_1",
        display_name="协作室1",
        coordinator_agent_id="coordinator_sam",
        member_peer_ids=("arch_guanlan", "arch_hengyue", "arch_jingchuan"),
        shared_topic_id="topic_1",
        routing_policy="coordinator_first",
    )
    router = RoomMessageRouter(room)

    # 普通消息 -> 协调者单点收敛
    recipients = router.route_message("请帮我梳理一下系统目前的架构方案")
    assert recipients == ("coordinator_sam",)

    # 显式 @ 专家消息 -> 转交对应专家
    recipients_mention = router.route_message("请问 @观澜 这里的契约边界是否足够严谨？")
    assert "arch_guanlan" in recipients_mention


def test_room_message_router_mention_only():
    room = RoomSpec(
        room_id="room_2",
        display_name="协作室2",
        coordinator_agent_id="coordinator_sam",
        member_peer_ids=("arch_guanlan", "arch_hengyue", "arch_jingchuan"),
        shared_topic_id="topic_2",
        routing_policy="mention_only",
    )
    router = RoomMessageRouter(room)

    # 未 @ 任何人 -> 默认不唤醒
    recipients = router.route_message("大家怎么看？")
    assert recipients == ()

    # 显式 @ 衡岳 -> 唤醒衡岳
    recipients_mention = router.route_message("@衡岳 请核查状态机迁移")
    assert recipients_mention == ("arch_hengyue",)
