'use client';

import { Flexbox, Tag } from '@lobehub/ui';
import { Collapse } from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useMemo } from 'react';

const styles = createStaticStyles(({ css, token }) => {
  return {
    container: css`
      border: 1px solid ${token.colorBorderSecondary};
      background: ${token.colorFillQuaternary};
      border-radius: ${token.borderRadius}px;
      padding: 8px 12px;
      margin-bottom: 8px;
      width: 100%;
      font-size: 13px;
    `,
    title: css`
      font-weight: 600;
      color: ${token.colorTextSecondary};
      margin-right: 8px;
    `,
    tagGroup: css`
      flex-wrap: wrap;
      gap: 6px;
    `,
    collapse: css`
      margin-top: 8px;
      background: transparent !important;
      border: none !important;

      .ant-collapse-item {
        border-bottom: 1px solid ${token.colorBorderSecondary} !important;
      }
      .ant-collapse-header {
        padding: 4px 8px !important;
        font-size: 12px !important;
        color: ${token.colorTextSecondary} !important;
      }
      .ant-collapse-content-box {
        padding: 6px 12px !important;
        font-size: 12px !important;
        background: ${token.colorBgContainer};
        border-radius: ${token.borderRadiusSM}px;
      }
    `,
  };
});

interface CollaborationTeamBarProps {
  content?: string | any;
  extra?: any;
  metadata?: any;
}

export const CollaborationTeamBar = memo<CollaborationTeamBarProps>(({ content, extra, metadata }) => {
  const isCollaboration = useMemo(() => {
    if (extra?.collaboration || metadata?.collaboration) return true;
    if (typeof content === 'string') {
      return (
        content.includes('【架构协同汇报') ||
        content.includes('【架构三角') ||
        (content.includes('观澜') && content.includes('衡岳') && content.includes('镜川'))
      );
    }
    return false;
  }, [content, extra, metadata]);

  if (!isCollaboration) return null;

  return (
    <Flexbox className={styles.container}>
      <Flexbox horizontal align="center" justify="space-between" width="100%">
        <Flexbox horizontal align="center" gap={4}>
          <span className={styles.title}>👥 架构协同三角已组队:</span>
          <Flexbox horizontal className={styles.tagGroup}>
            <Tag color="blue">📐 观澜 · 边界与契约</Tag>
            <Tag color="gold">⚖️ 衡岳 · 状态机与不变量</Tag>
            <Tag color="purple">🔍 镜川 · 对抗审计</Tag>
          </Flexbox>
        </Flexbox>
        <Tag color="green">已收敛汇总</Tag>
      </Flexbox>
    </Flexbox>
  );
});

export default CollaborationTeamBar;
