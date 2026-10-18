'use client';

import React, { memo, useCallback, useMemo } from 'react';
import {
  GlobalOutlined,
  RightOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Button, Card, Flex, Space, Tag, Typography } from 'antd';
import { createStaticStyles } from 'antd-style';

const { Text, Paragraph } = Typography;

export interface BrowserPreviewCardPayload {
  sessionId: string;
  url: string;
  title?: string;
  status?: string;
  runId?: string;
  screenshotUrl?: string;
}

export interface BrowserPreviewCardProps {
  content?: string;
  payload?: BrowserPreviewCardPayload;
  tools?: any[];
  className?: string;
  style?: React.CSSProperties;
}

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    card: css`
      background: ${cssVar.colorBgElevated};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 12px;
      padding: 12px 14px;
      margin: 8px 0;
      max-width: 520px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
      transition: all 0.2s ease;

      &:hover {
        border-color: ${cssVar.colorPrimaryHover};
      }
    `,
    header: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    `,
    titleText: css`
      font-weight: 600;
      font-size: 14px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    `,
    urlText: css`
      color: ${cssVar.colorTextTertiary};
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    `,
    previewBox: css`
      background: #fff;
      border: 1px solid #e5e5e5;
      border-radius: 6px;
      height: 120px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: ${cssVar.colorTextSecondary};
      font-size: 12px;
      margin-bottom: 10px;
      cursor: pointer;
      overflow: hidden;
      position: relative;
    `,
  };
});

function previewSessionId(url: string): string {
  let hash = 0;
  for (let i = 0; i < url.length; i += 1) {
    hash = (hash * 31 + url.charCodeAt(i)) >>> 0;
  }
  return `brw_preview_${hash.toString(16)}`;
}

export const BrowserPreviewCard: React.FC<BrowserPreviewCardProps> = memo(({
  content,
  payload: directPayload,
  tools,
  className,
  style,
}) => {
  const [sessions, setSessions] = React.useState<
    { sessionId: string; url: string; title: string }[]
  >([]);

  // Live sessions are matched to this card by URL. The list order is not
  // the page the user asked to open.
  React.useEffect(() => {
    let cancelled = false;
    const fetchSessions = async () => {
      try {
        const res = await fetch('/lca-api/browser/sessions');
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled || !Array.isArray(data.sessions)) return;
        setSessions(
          data.sessions.map((row: { session_id?: string; url?: string; title?: string }) => ({
            sessionId: row.session_id || '',
            url: row.url || '',
            title: row.title || '',
          })),
        );
      } catch {
        // ignore
      }
    };
    fetchSessions();
    return () => {
      cancelled = true;
    };
  }, []);

  // 从 Markdown 内容 或 tools 中解析
  const parsedPayload = useMemo(() => {
    if (directPayload) return directPayload;

    if (content) {
      const match = content.match(/\[widget:browser_preview\?([^\]]+)\]/);
      if (match) {
        const params = new URLSearchParams(match[1]);
        return {
          sessionId: params.get('sessionId') || '',
          url: params.get('url') || 'about:blank',
          title: params.get('title') || 'Browser Tab',
          status: params.get('status') || 'idle',
          runId: params.get('runId') || undefined,
        } as BrowserPreviewCardPayload;
      }
    }

    if (tools && Array.isArray(tools)) {
      const browserTool = tools.find((t: any) =>
        t?.apiName &&
        [
          'browser_open',
          'browser_navigate',
          'browser_spawn_task',
          'browser_steer_task',
          'browser_transfer_task',
        ].includes(t.apiName),
      );
      if (browserTool) {
        let args: any = {};
        try {
          args =
            typeof browserTool.arguments === 'string'
              ? JSON.parse(browserTool.arguments)
              : browserTool.arguments || {};
        } catch {
          args = {};
        }
        const requestedUrl = args.url || args.initial_url || '';
        const matched = sessions.find((row) => row.url && requestedUrl && row.url === requestedUrl);
        const u = requestedUrl || matched?.url || '';
        const sid =
          args.sessionId ||
          args.session_id ||
          matched?.sessionId ||
          (u ? previewSessionId(u) : '');
        const t = args.title || (matched?.url === u ? matched.title : '') || u || 'Browser Tab';
        if (!sid && !u) return null;
        return {
          sessionId: sid,
          url: u,
          title: t,
          status: 'agent_running',
        } as BrowserPreviewCardPayload;
      }
    }

    return null;
  }, [content, directPayload, tools, sessions]);

  const payload = parsedPayload;

  const handleOpenDrawer = useCallback((takeover: boolean = false) => {
    if (!payload) return;
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('lca:open_browser_drawer', {
          detail: {
            sessionId: payload.sessionId,
            url: payload.url,
            title: payload.title,
            status: payload.status,
            takeover,
          },
        }),
      );
    }
  }, [payload]);

  // 当收到有效的真实浏览器会话时，自动唤起一次右侧栏抽屉（对齐 Grok/Muse 实时视口体验）
  React.useEffect(() => {
    if (!payload?.sessionId) return;
    const sid = payload.sessionId;
    const storageKey = `lca_browser_drawer_auto_opened_${sid}`;
    if (typeof window !== 'undefined') {
      try {
        if (!sessionStorage.getItem(storageKey)) {
          const timer = setTimeout(() => {
            handleOpenDrawer(false);
          }, 400);
          return () => clearTimeout(timer);
        }
      } catch {
        handleOpenDrawer(false);
      }
    }
  }, [payload?.sessionId, handleOpenDrawer]);

  if (!payload) return null;

  const isTakeover = payload.status === 'human_takeover';


  return (
    <div className={styles.card} style={style}>
      <div className={styles.header}>
        <Space size={8} style={{ overflow: 'hidden' }}>
          <GlobalOutlined style={{ fontSize: 16, color: '#1677ff' }} />
          <div style={{ overflow: 'hidden' }}>
            <div className={styles.titleText}>{payload.title || 'Browser Session'}</div>
            <div className={styles.urlText}>{payload.url}</div>
          </div>
        </Space>
        <Tag color={isTakeover ? 'green' : 'orange'}>
          {isTakeover ? '人工接管' : 'AI 运行中'}
        </Tag>
      </div>

      <div className={styles.previewBox} onClick={() => handleOpenDrawer(false)}>
        <Flex vertical align="center" gap={4}>
          <ThunderboltOutlined style={{ fontSize: 24, color: '#1677ff' }} />
          <span>点击打开实时浏览器抽屉</span>
        </Flex>
      </div>

      <Flex justify="space-between" align="center">
        <Button
          size="small"
          type="primary"
          ghost
          icon={<RightOutlined />}
          onClick={() => handleOpenDrawer(false)}
        >
          查看实时画面
        </Button>

        <Button
          size="small"
          type="primary"
          icon={<ThunderboltOutlined />}
          onClick={() => handleOpenDrawer(true)}
        >
          接管操作
        </Button>
      </Flex>
    </div>
  );
});

BrowserPreviewCard.displayName = 'BrowserPreviewCard';
export default BrowserPreviewCard;
