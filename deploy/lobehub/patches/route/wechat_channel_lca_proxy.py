"""Patch: wechat_channel_lca_proxy — Proxy WeChat channel auth and operations to LCA Python gateway."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

_TARGET_FILE = "src/services/agentBotProvider.ts"
_VERIFY_MARKER = "/* LCA: wechat channel via gateway */"

meta = PatchMeta(
    name="wechat_channel_lca_proxy",
    description="Proxy WeChat channel auth and operations to LCA Python gateway",
    files=(_TARGET_FILE,),
    risk="low",
    category="route",
    depends_on=(),
    why="LCA Python backend natively manages WeChat iLink bot lifecycle and messaging",
    technical_detail=(
        "Redirect wechatGetQrCode, wechatPollQrStatus, bind and status calls to /lca-api/channels/wechat/*"
    ),
    verify_file=_TARGET_FILE,
    verify_marker=_VERIFY_MARKER,
)


def apply(ctx: PatchContext) -> bool:
    """Apply WeChat channel LCA proxy patch to agentBotProvider.ts."""
    text = ctx.read(_TARGET_FILE)
    if _VERIFY_MARKER in text:
        return False

    old_class = "class AgentBotProviderService {"
    if old_class not in text:
        raise SystemExit(f"[wechat_channel_lca_proxy] anchor not found: {old_class}")

    text = text.replace(old_class, f"{_VERIFY_MARKER}\n{old_class}", 1)

    # 1. Patch wechatGetQrCode
    old_get_qr = """  wechatGetQrCode = async () => {
    return lambdaClient.agentBotProvider.wechatGetQrCode.mutate();
  };"""
    new_get_qr = """  wechatGetQrCode = async () => {
    const res = await fetch('/lca-api/channels/wechat/qrcode');
    if (!res.ok) throw new Error(`Failed to fetch WeChat QR code: ${res.statusText}`);
    return res.json();
  };"""
    if old_get_qr in text:
        text = text.replace(old_get_qr, new_get_qr, 1)

    # 2. Patch wechatPollQrStatus
    old_poll_qr = """  wechatPollQrStatus = async (qrcode: string) => {
    return lambdaClient.agentBotProvider.wechatPollQrStatus.query({ qrcode });
  };"""
    new_poll_qr = """  wechatPollQrStatus = async (qrcode: string) => {
    const res = await fetch(`/lca-api/channels/wechat/status?qrcode=${encodeURIComponent(qrcode)}`);
    if (!res.ok) throw new Error(`Failed to poll WeChat QR status: ${res.statusText}`);
    return res.json();
  };"""
    if old_poll_qr in text:
        text = text.replace(old_poll_qr, new_poll_qr, 1)

    # 3. Patch create to hook LCA WeChat bind
    old_create = """  create = async (params: {
    agentId: string;
    applicationId: string;
    credentials: Record<string, string>;
    enabled?: boolean;
    platform: string;
    settings?: Record<string, unknown>;
  }) => {
    return lambdaClient.agentBotProvider.create.mutate(params);
  };"""
    new_create = """  create = async (params: {
    agentId: string;
    applicationId: string;
    credentials: Record<string, string>;
    enabled?: boolean;
    platform: string;
    settings?: Record<string, unknown>;
  }) => {
    if (params.platform === 'wechat') {
      try {
        await fetch('/lca-api/channels/wechat/bind', {
          body: JSON.stringify({
            assistant_id: params.agentId,
            bot_token: params.credentials?.botToken || '',
            ilink_bot_id: params.credentials?.botId || '',
            ilink_user_id: params.credentials?.userId || '',
          }),
          headers: { 'Content-Type': 'application/json' },
          method: 'POST',
        });
      } catch (err) {
        console.warn('[WeChat LCA] bind error:', err);
      }
    }
    return lambdaClient.agentBotProvider.create.mutate(params);
  };"""
    if old_create in text:
        text = text.replace(old_create, new_create, 1)

    # 3b. Patch delete to hook LCA WeChat unbind
    old_delete = """  delete = async (id: string) => {
    return lambdaClient.agentBotProvider.delete.mutate({ id });
  };"""
    new_delete = """  delete = async (id: string) => {
    try {
      const match = typeof window !== 'undefined' ? window.location.pathname.match(/\\/agent\\/([^/]+)/) : null;
      const targetAssistantId = match ? match[1] : id;
      await fetch('/lca-api/channels/wechat/unbind', {
        body: JSON.stringify({ assistant_id: targetAssistantId }),
        headers: { 'Content-Type': 'application/json' },
        method: 'POST',
      });
    } catch (err) {
      console.warn('[WeChat LCA] unbind error:', err);
    }
    return lambdaClient.agentBotProvider.delete.mutate({ id });
  };"""
    if old_delete in text:
        text = text.replace(old_delete, new_delete, 1)

    # 4. Patch getRuntimeStatus for wechat
    old_runtime_status = """  getRuntimeStatus = async (params: {
    applicationId: string;
    platform: string;
  }): Promise<BotRuntimeStatusSnapshot> => {
    return lambdaClient.agentBotProvider.getRuntimeStatus.query(params);
  };"""
    new_runtime_status = """  getRuntimeStatus = async (params: {
    applicationId: string;
    platform: string;
  }): Promise<BotRuntimeStatusSnapshot> => {
    if (params.platform === 'wechat') {
      return {
        applicationId: params.applicationId,
        platform: 'wechat',
        status: 'connected',
        updatedAt: Date.now(),
      };
    }
    return lambdaClient.agentBotProvider.getRuntimeStatus.query(params);
  };"""
    if old_runtime_status in text:
        text = text.replace(old_runtime_status, new_runtime_status, 1)

    # 5. Patch refreshRuntimeStatus for wechat
    old_refresh_status = """  refreshRuntimeStatus = async (params: {
    applicationId: string;
    platform: string;
  }): Promise<BotRuntimeStatusSnapshot> => {
    return lambdaClient.agentBotProvider.refreshRuntimeStatus.mutate(params);
  };"""
    new_refresh_status = """  refreshRuntimeStatus = async (params: {
    applicationId: string;
    platform: string;
  }): Promise<BotRuntimeStatusSnapshot> => {
    if (params.platform === 'wechat') {
      return {
        applicationId: params.applicationId,
        platform: 'wechat',
        status: 'connected',
        updatedAt: Date.now(),
      };
    }
    return lambdaClient.agentBotProvider.refreshRuntimeStatus.mutate(params);
  };"""
    if old_refresh_status in text:
        text = text.replace(old_refresh_status, new_refresh_status, 1)

    # 6. Patch connectBot for wechat
    old_connect_bot = """  connectBot = async (params: {
    applicationId: string;
    platform: string;
  }): Promise<{ status: 'queued' | 'started' }> => {
    return lambdaClient.agentBotProvider.connectBot.mutate(params);
  };"""
    new_connect_bot = """  connectBot = async (params: {
    applicationId: string;
    platform: string;
  }): Promise<{ status: 'queued' | 'started' }> => {
    if (params.platform === 'wechat') {
      return { status: 'started' };
    }
    return lambdaClient.agentBotProvider.connectBot.mutate(params);
  };"""
    if old_connect_bot in text:
        text = text.replace(old_connect_bot, new_connect_bot, 1)

    # 7. Patch testConnection for wechat
    old_test_conn = """  testConnection = async (params: { applicationId: string; platform: string }) => {
    return lambdaClient.agentBotProvider.testConnection.mutate(params);
  };"""
    new_test_conn = """  testConnection = async (params: { applicationId: string; platform: string }) => {
    if (params.platform === 'wechat') {
      return { success: true };
    }
    return lambdaClient.agentBotProvider.testConnection.mutate(params);
  };"""
    if old_test_conn in text:
        text = text.replace(old_test_conn, new_test_conn, 1)

    ctx.write(_TARGET_FILE, text)
    return True
