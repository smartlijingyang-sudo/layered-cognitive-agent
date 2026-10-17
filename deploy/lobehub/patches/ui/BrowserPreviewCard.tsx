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
      background: #111;
      border-radius: 6px;
      height: 120px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: rgba(255, 255, 255, 0.45);
      font-size: 12px;
      margin-bottom: 10px;
      cursor: pointer;
      overflow: hidden;
      position: relative;
    `,
  };
});

export const BrowserPreviewCard: React.FC<BrowserPreviewCardProps> = memo(({
  content,
  payload: directPayload,
  className,
  style,
}) => {
  // 从 Markdown 内容中解析 [widget:browser_preview?sessionId=...&url=...]
  const parsedPayload = useMemo(() => {
    if (directPayload) return directPayload;
    if (!content) return null;

    const match = content.match(/\[widget:browser_preview\?([^\]]+)\]/);
    if (!match) return null;

    const params = new URLSearchParams(match[1]);
    return {
      sessionId: params.get('sessionId') || 'default',
      url: params.get('url') || 'about:blank',
      title: params.get('title') || 'Browser Tab',
      status: params.get('status') || 'idle',
      runId: params.get('runId') || undefined,
    } as BrowserPreviewCardPayload;
  }, [content, directPayload]);

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
