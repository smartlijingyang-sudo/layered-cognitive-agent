'use client';

import { Flexbox, Tag } from '@lobehub/ui';
import { Collapse } from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useMemo } from 'react';

const TAG_COLORS = ['blue', 'purple', 'cyan', 'gold', 'geekblue', 'magenta', 'lime', 'orange'];

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    container: css`
      border: 1px solid ${cssVar.colorBorderSecondary};
      background: ${cssVar.colorFillQuaternary};
      border-radius: ${cssVar.borderRadius};
      padding: 8px 12px;
      margin-bottom: 8px;
      width: 100%;
      font-size: 13px;
    `,
    title: css`
      font-weight: 600;
      color: ${cssVar.colorTextSecondary};
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
        border-bottom: 1px solid ${cssVar.colorBorderSecondary} !important;
      }
      .ant-collapse-header {
        padding: 4px 8px !important;
        font-size: 12px !important;
        color: ${cssVar.colorTextSecondary} !important;
      }
      .ant-collapse-content-box {
        padding: 6px 12px !important;
        font-size: 12px !important;
        background: ${cssVar.colorBgContainer};
        border-radius: ${cssVar.borderRadiusSM};
        white-space: pre-wrap;
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
        content.includes('【协同汇报') ||
        content.includes('【多Agent协同') ||
        content.includes('【架构协同汇报') ||
        content.includes('【架构三角')
      );
    }
    return false;
  }, [content, extra, metadata]);

  const findings: Record<string, string> = useMemo(() => {
    return (
      extra?.collaboration?.member_findings ||
      metadata?.collaboration?.member_findings ||
      {}
    );
  }, [extra, metadata]);

  const memberMeta: Record<string, any> = useMemo(() => {
    return (
      extra?.collaboration?.member_metadata ||
      metadata?.collaboration?.member_metadata ||
      {}
    );
  }, [extra, metadata]);

  const consensusStatus = useMemo(() => {
    return (
      extra?.collaboration?.consensus_status ||
      metadata?.collaboration?.consensus_status ||
      'unanimous'
    );
  }, [extra, metadata]);

  const getPeerDisplay = (peerId: string, idx: number) => {
    const meta = memberMeta[peerId];
    const name = meta?.name || peerId.split('/').pop()?.replace(/^arch_/, '') || peerId;
    const emoji = meta?.emoji || '🔍';
    const color = TAG_COLORS[idx % TAG_COLORS.length];
    return { name, emoji, color };
  };

  // 提取各专家的独立分析结论并动态生成 Collapse 面板
  const collapseItems = useMemo(() => {
    if (!isCollaboration) return [];
    const entries = Object.entries(findings);
    if (entries.length === 0) return [];

    return entries.map(([peerId, text], idx) => {
      const info = getPeerDisplay(peerId, idx);
      return {
        key: peerId,
        label: `${info.emoji} ${info.name} · 专家审查详情`,
        children: <div>{String(text)}</div>,
      };
    });
  }, [isCollaboration, findings, memberMeta]);

  if (!isCollaboration) return null;

  const peerKeys = Object.keys(findings);

  return (
    <Flexbox className={styles.container}>
      <Flexbox horizontal align="center" justify="space-between" width="100%">
        <Flexbox horizontal align="center" gap={4}>
          <span className={styles.title}>👥 专家协同团队已组队:</span>
          <Flexbox horizontal className={styles.tagGroup}>
            {peerKeys.length > 0 ? (
              peerKeys.map((peerId, idx) => {
                const info = getPeerDisplay(peerId, idx);
                return (
                  <Tag key={peerId} color={info.color}>
                    {info.emoji} {info.name}
                  </Tag>
                );
              })
            ) : (
              <Tag color="blue">👥 专家协同</Tag>
            )}
          </Flexbox>
        </Flexbox>
        <Tag color={consensusStatus === 'unanimous' ? 'green' : 'orange'}>
          {consensusStatus === 'unanimous' ? '已收敛汇总' : '部分降级收敛'}
        </Tag>
      </Flexbox>
      {collapseItems.length > 0 && (
        <Collapse
          ghost
          size="small"
          className={styles.collapse}
          items={collapseItems}
        />
      )}
    </Flexbox>
  );
});

export default CollaborationTeamBar;
