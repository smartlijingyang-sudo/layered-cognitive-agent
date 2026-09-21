'use client';

/**
 * LCA: conversational "连接本机" intent.
 * Intercept chat send → confirm modal → preauth → trigger local install
 * (download .cmd + clipboard + optional custom protocol) → poll devices → bind.
 */
import { confirmModal } from '@lobehub/ui/base-ui';
import { memo, useCallback, useEffect, useRef } from 'react';

import { message } from '@/components/AntdStaticMethods';
import { useSelectExecutionTarget } from '@/features/ChatInput/hooks/useSelectExecutionTarget';
import { useConversationStore } from '@/features/Conversation/store';

const INTENT_RE =
  /^(连接本机|连接我的电脑|接入本机|连一下本机|connect\s*(my\s*)?(local\s*)?(machine|computer|pc))\s*[!！.。]?$/i;

const EVENT = 'lca:connect-local-intent';

type IntentDetail = {
  clearContent?: () => void;
  message?: string;
};

type PreauthResp = {
  success?: boolean;
  userCode?: string;
  installCommands?: { windows?: string; bash?: string };
  expiresIn?: number;
};

type LcaDevice = {
  deviceId: string;
  hostname?: string;
  friendlyName?: string;
  online?: boolean;
};

const isWindows = () =>
  typeof navigator !== 'undefined' && /Win/i.test(navigator.platform || navigator.userAgent);

const downloadCmdLauncher = (installCmd: string) => {
  // .cmd so Windows SmartScreen / download bar can "Open" with one click
  const body =
    '@echo off\r\n' +
    'chcp 65001 >nul\r\n' +
    'echo LCA Companion auto-install...\r\n' +
    'powershell -NoProfile -ExecutionPolicy Bypass -Command "' +
    installCmd.replace(/"/g, '`"') +
    '"\r\n' +
    'if errorlevel 1 pause\r\n';
  const blob = new Blob([body], { type: 'application/x-bat' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'LCA-Connect-Local.cmd';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
};

const tryProtocol = (code: string) => {
  try {
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    iframe.src = `lca-companion://pair?code=${encodeURIComponent(code)}`;
    document.body.appendChild(iframe);
    window.setTimeout(() => iframe.remove(), 2000);
  } catch {
    /* protocol may be unregistered on first install */
  }
};

async function fetchPreauth(): Promise<PreauthResp> {
  const resp = await fetch('/lca-api/api/device/pair/preauth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  return (await resp.json()) as PreauthResp;
}

async function listLcaDevices(): Promise<LcaDevice[]> {
  try {
    const resp = await fetch('/lca-api/api/device/devices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!resp.ok) return [];
    const body = (await resp.json()) as { devices?: LcaDevice[] };
    return Array.isArray(body.devices) ? body.devices : [];
  } catch {
    return [];
  }
}

const ConnectLocalIntent = memo(() => {
  const agentId = useConversationStore((s) => s.context.agentId) || '';
  const selectExecutionTarget = useSelectExecutionTarget(agentId);
  const busyRef = useRef(false);
  const knownOnlineRef = useRef<Set<string>>(new Set());

  const runConnect = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    const hide = message.loading('正在准备本机连接…', 0);
    try {
      const before = await listLcaDevices();
      knownOnlineRef.current = new Set(
        before.filter((d) => d.online).map((d) => d.deviceId),
      );

      const data = await fetchPreauth();
      if (!data.success || !data.installCommands) {
        message.error('预授权失败，请稍后重试');
        return;
      }

      const win = isWindows();
      const installCmd = win
        ? data.installCommands.windows || ''
        : data.installCommands.bash || '';
      const code = data.userCode || '';

      if (installCmd) {
        try {
          await navigator.clipboard.writeText(installCmd);
        } catch {
          /* clipboard may be denied */
        }
      }

      if (win && installCmd) {
        downloadCmdLauncher(installCmd);
      }
      if (code) tryProtocol(code);

      hide();
      message.info(
        win
          ? '已下载 LCA-Connect-Local.cmd，请打开下载栏点击「打开」完成安装（命令已复制到剪贴板作备用）'
          : '安装命令已复制，请在本机终端粘贴回车',
        8,
      );

      const deadline = Date.now() + Math.min((data.expiresIn || 600) * 1000, 10 * 60 * 1000);
      const pollHide = message.loading('等待本机 Companion 上线…', 0);
      let bound = false;
      while (Date.now() < deadline && !bound) {
        await new Promise((r) => window.setTimeout(r, 2000));
        const devices = await listLcaDevices();
        const newly = devices.find(
          (d) => d.online && !knownOnlineRef.current.has(d.deviceId),
        );
        const anyOnline = devices.find((d) => d.online);
        const target = newly || (knownOnlineRef.current.size === 0 ? anyOnline : undefined);
        if (target?.deviceId && selectExecutionTarget) {
          await selectExecutionTarget('device', target.deviceId);
          bound = true;
          pollHide();
          message.success(
            `本机已连接：${target.friendlyName || target.hostname || target.deviceId}，可直接操作本机目录`,
            6,
          );
          break;
        }
      }
      if (!bound) {
        pollHide();
        message.warning(
          '尚未检测到本机上线。请确认已运行下载的安装脚本，或在终端执行剪贴板中的命令。',
          10,
        );
      }
    } catch (err) {
      hide();
      message.error(`连接本机失败：${(err as Error).message || String(err)}`);
    } finally {
      busyRef.current = false;
    }
  }, [selectExecutionTarget]);

  useEffect(() => {
    const onIntent = (ev: Event) => {
      const detail = (ev as CustomEvent<IntentDetail>).detail || {};
      detail.clearContent?.();

      confirmModal({
        title: '连接本机',
        content:
          '确认后将下载并启动本机 Companion（需在下载栏点一次「打开」）。安装完成后本会话会自动切到本机执行，可读写本机目录。',
        okText: '确认连接',
        cancelText: '取消',
        onOk: () => {
          void runConnect();
        },
      });
    };
    window.addEventListener(EVENT, onIntent as EventListener);
    return () => window.removeEventListener(EVENT, onIntent as EventListener);
  }, [runConnect]);

  return null;
});

ConnectLocalIntent.displayName = 'ConnectLocalIntent';

export default ConnectLocalIntent;
export { INTENT_RE, EVENT as CONNECT_LOCAL_INTENT_EVENT };
