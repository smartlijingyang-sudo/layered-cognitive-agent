from unittest.mock import AsyncMock, call

import pytest

from lca.contracts.channels.wechat import WechatChannelConfig
from lca.infrastructure.channels.wechat.manager import WechatChannelManager
from lca.infrastructure.channels.wechat.worker import (
    WechatChannelWorker,
    derive_wechat_session_id,
)


def test_derive_wechat_session_id():
    sess_1 = derive_wechat_session_id("asst_12345678", "user_abc@im.wechat")
    sess_2 = derive_wechat_session_id("asst_12345678", "user_abc@im.wechat")
    sess_diff_user = derive_wechat_session_id("asst_12345678", "user_xyz@im.wechat")
    sess_diff_asst = derive_wechat_session_id("asst_87654321", "user_abc@im.wechat")

    assert sess_1 == sess_2
    assert sess_1.startswith("sess_wc_")
    assert sess_1 != sess_diff_user
    assert sess_1 != sess_diff_asst


@pytest.mark.asyncio
async def test_worker_processes_inbound_message():
    client = AsyncMock()
    client.get_updates.return_value = {
        "ret": 0,
        "get_updates_buf": "cursor_1",
        "msgs": [
            {
                "from_user_id": "user_wechat_1@im.wechat",
                "context_token": "ctx_token_999",
                "item_list": [{"type": 1, "text_item": {"text": "你好，能帮我查下磁盘吗？"}}],
            }
        ],
    }
    client.send_typing.return_value = True
    client.send_message.return_value = True

    dispatched_runs = []

    async def mock_dispatch(assistant_id: str, session_id: str, text: str, progress_callback=None):
        dispatched_runs.append((assistant_id, session_id, text))
        if progress_callback:
            await progress_callback("💭 正在分析磁盘...")
        return "磁盘剩余 30GB，使用率 40%。"

    config = WechatChannelConfig(
        bot_id="bot_1@im.bot",
        bot_token="token_abc",  # noqa: S106
        user_id="user_owner@im.wechat",
        display_tool_calls=True,
    )

    worker = WechatChannelWorker(
        assistant_id="asst_arch_1",
        config=config,
        client=client,
        dispatch_fn=mock_dispatch,
    )

    # Run single polling iteration
    await worker.poll_step()

    # Verify dispatch occurred with mapped session
    assert len(dispatched_runs) == 1
    asst_id, sess_id, text = dispatched_runs[0]
    assert asst_id == "asst_arch_1"
    assert sess_id.startswith("sess_wc_")
    assert text == "你好，能帮我查下磁盘吗？"

    # Verify typing was sent (start=True, then start=False)
    client.send_typing.assert_has_calls([
        call("token_abc", "user_wechat_1@im.wechat", "", start=True),
        call("token_abc", "user_wechat_1@im.wechat", "", start=False),
    ])

    # Verify progress was sent (because display_tool_calls=True)
    assert any("正在分析磁盘" in str(call) for call in client.send_message.call_args_list)

    # Verify final message was sent with context_token
    assert any("磁盘剩余 30GB" in str(call) for call in client.send_message.call_args_list)
    assert any("ctx_token_999" in str(call) for call in client.send_message.call_args_list)


@pytest.mark.asyncio
async def test_manager_bind_and_unbind(tmp_path):
    manager = WechatChannelManager(base_dir=tmp_path)
    config = WechatChannelConfig(
        bot_id="bot_test@im.bot",
        bot_token="token_123",  # noqa: S106
        user_id="user_test@im.wechat",
        enabled=True,
    )

    # Bind assistant
    await manager.bind_channel("asst_001", config)
    assert manager.is_running("asst_001")

    # Config must be persisted to disk
    config_file = tmp_path / "assistants" / "asst_001" / "channels" / "wechat.json"
    assert config_file.exists()

    # Unbind assistant
    await manager.unbind_channel("asst_001")
    assert not manager.is_running("asst_001")
    assert not config_file.exists()

    await manager.shutdown()
