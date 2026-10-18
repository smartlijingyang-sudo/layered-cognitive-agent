'use client';

import React, { memo, useCallback, useState } from 'react';
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  GlobalOutlined,
  ReloadOutlined,
  SwapOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Button, Input, Space, Tag, Typography } from 'antd';
import { createStaticStyles } from 'antd-style';

const { Text } = Typography;

export interface BrowserToolbarProps {
  url: string;
  title: string;
  status: string;
  onNavigate?: (url: string) => void;
  onReload?: () => void;
  onToggleTakeover?: (takeover: boolean) => void;
  className?: string;
  style?: React.CSSProperties;
}

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    toolbar: css`
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      background: #fff;
      border-bottom: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 8px 8px 0 0;
    `,
    urlInput: css`
      flex: 1;
      font-size: 13px;
    `,
  };
});

export const BrowserToolbar: React.FC<BrowserToolbarProps> = memo(({
  url,
  title,
  status,
  onNavigate,
  onReload,
  onToggleTakeover,
  className,
  style,
}) => {
  const [currentUrl, setCurrentUrl] = useState<string>(url);
  const isTakeover = status === 'human_takeover';

  const handleUrlSubmit = useCallback(() => {
    if (onNavigate && currentUrl) {
      onNavigate(currentUrl);
    }
  }, [currentUrl, onNavigate]);

  return (
    <div className={styles.toolbar} style={style}>
      <Space orientation="horizontal" size={4}>
        <Button size="small" icon={<ArrowLeftOutlined />} disabled />
        <Button size="small" icon={<ArrowRightOutlined />} disabled />
        <Button size="small" icon={<ReloadOutlined />} onClick={onReload} />
      </Space>

      <Input
        size="small"
        prefix={<GlobalOutlined />}
        value={currentUrl}
        onChange={(e) => setCurrentUrl(e.target.value)}
        onPressEnter={handleUrlSubmit}
        className={styles.urlInput}
        placeholder="https://..."
      />

      <Space orientation="horizontal" size={8}>
        {isTakeover ? (
          <Button
            size="small"
            type="primary"
            danger
            icon={<SwapOutlined />}
            onClick={() => onToggleTakeover && onToggleTakeover(false)}
          >
            交还 AI
          </Button>
        ) : (
          <Button
            size="small"
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={() => onToggleTakeover && onToggleTakeover(true)}
          >
            接管操作
          </Button>
        )}

        <Tag color={isTakeover ? 'green' : 'orange'}>
          {isTakeover ? '人工接管' : 'AI 运行'}
        </Tag>
      </Space>
    </div>
  );
});

BrowserToolbar.displayName = 'BrowserToolbar';
export default BrowserToolbar;
