"""Tests for wechat_channel_lca_proxy frontend route patch."""

from __future__ import annotations

from deploy.lobehub.engine import discover_patches
from deploy.lobehub.patches.route.wechat_channel_lca_proxy import apply, meta

_STUB_PROVIDER = """import { lambdaClient } from '@/libs/trpc/client';

import type { BotRuntimeStatusSnapshot } from '../types/botRuntimeStatus';

class AgentBotProviderService {
  listPlatforms = async () => {
    return lambdaClient.agentBotProvider.listPlatforms.query();
  };

  getByAgentId = async (agentId: string) => {
    return lambdaClient.agentBotProvider.getByAgentId.query({ agentId });
  };

  getRuntimeStatus = async (params: {
    applicationId: string;
    platform: string;
  }): Promise<BotRuntimeStatusSnapshot> => {
    return lambdaClient.agentBotProvider.getRuntimeStatus.query(params);
  };

  refreshRuntimeStatus = async (params: {
    applicationId: string;
    platform: string;
  }): Promise<BotRuntimeStatusSnapshot> => {
    return lambdaClient.agentBotProvider.refreshRuntimeStatus.mutate(params);
  };

  refreshRuntimeStatusesByAgent = async (agentId: string): Promise<void> => {
    await lambdaClient.agentBotProvider.refreshRuntimeStatusesByAgent.mutate({ agentId });
  };

  create = async (params: {
    agentId: string;
    applicationId: string;
    credentials: Record<string, string>;
    enabled?: boolean;
    platform: string;
    settings?: Record<string, unknown>;
  }) => {
    return lambdaClient.agentBotProvider.create.mutate(params);
  };

  update = async (
    id: string,
    params: {
      applicationId?: string;
      credentials?: Record<string, string>;
      enabled?: boolean;
      platform?: string;
      settings?: Record<string, unknown>;
    },
  ) => {
    return lambdaClient.agentBotProvider.update.mutate({ id, ...params });
  };

  delete = async (id: string) => {
    return lambdaClient.agentBotProvider.delete.mutate({ id });
  };

  connectBot = async (params: {
    applicationId: string;
    platform: string;
  }): Promise<{ status: 'queued' | 'started' }> => {
    return lambdaClient.agentBotProvider.connectBot.mutate(params);
  };

  testConnection = async (params: { applicationId: string; platform: string }) => {
    return lambdaClient.agentBotProvider.testConnection.mutate(params);
  };

  lineFetchBotInfo = async (channelAccessToken: string) => {
    return lambdaClient.agentBotProvider.lineFetchBotInfo.mutate({ channelAccessToken });
  };

  wechatGetQrCode = async () => {
    return lambdaClient.agentBotProvider.wechatGetQrCode.mutate();
  };

  wechatPollQrStatus = async (qrcode: string) => {
    return lambdaClient.agentBotProvider.wechatPollQrStatus.query({ qrcode });
  };
}

export const agentBotProviderService = new AgentBotProviderService();
"""


class _MockContext:
    def __init__(self, initial_text: str) -> None:
        self.files = {"src/services/agentBotProvider.ts": initial_text}

    def read(self, rel: str) -> str:
        if rel not in self.files:
            raise FileNotFoundError(f"File not found: {rel}")
        return self.files[rel]

    def write(self, rel: str, text: str) -> None:
        self.files[rel] = text

    def write_if_changed(self, rel: str, text: str) -> bool:
        if self.files.get(rel) == text:
            return False
        self.files[rel] = text
        return True


def test_wechat_patch_meta() -> None:
    assert meta.name == "wechat_channel_lca_proxy"
    assert meta.category == "route"
    assert "src/services/agentBotProvider.ts" in meta.files
    assert meta.verify_marker == "/* LCA: wechat channel via gateway */"


def test_wechat_patch_apply_and_idempotence() -> None:
    ctx = _MockContext(_STUB_PROVIDER)

    # First apply: returns True and updates content
    applied = apply(ctx)  # type: ignore[arg-type]
    assert applied is True
    content = ctx.read("src/services/agentBotProvider.ts")

    assert "/* LCA: wechat channel via gateway */" in content
    assert "/lca-api/channels/wechat/qrcode" in content
    assert "/lca-api/channels/wechat/status" in content
    assert "/lca-api/channels/wechat/bind" in content
    assert "params.platform === 'wechat'" in content

    # Second apply: idempotent, returns False
    applied_again = apply(ctx)  # type: ignore[arg-type]
    assert applied_again is False


def test_wechat_patch_discovered() -> None:
    all_patches = discover_patches()
    assert any(pm.meta.name == "wechat_channel_lca_proxy" for pm in all_patches)
