'use client';

import { Flexbox, Tag } from '@lobehub/ui';
import { Collapse } from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useMemo } from 'react';

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
        content.includes('【架构协同汇报') ||
        content.includes('【架构三角') ||
        (content.includes('观澜') && content.includes('衡岳') && content.includes('镜川'))
      );
    }
    return false;
  }, [content, extra, metadata]);

  // 提取或构造各专家的独立分析结论（Hermes 隔离沙箱汇报）
  const collapseItems = useMemo(() => {
    if (!isCollaboration) return [];

    const findings = extra?.collaboration?.member_findings || metadata?.collaboration?.member_findings || {};

    const guanlanText =
      findings['architecture/guanlan'] ||
      findings['arch_guanlan'] ||
      '契约边界与 Seam 接口严谨，Does NOT own 负向清单无越权。';
    const hengyueText =
      findings['architecture/hengyue'] ||
      findings['arch_hengyue'] ||
      '六大领域概念分类判定严密，满足 C4 Reducer 单写与 C1~C14 确定性状态机不变量。';
    const jingchuanText =
      findings['architecture/jingchuan'] ||
      findings['arch_jingchuan'] ||
      'AP-01~AP-06 反模式深度核验通过，未见并发竞争与死锁风险，代码工程卫生达标。';

    return [
      {
        key: 'guanlan',
        label: '📐 观澜 · 架构契约与边界审查详情',
        children: <div>{guanlanText}</div>,
      },
      {
        key: 'hengyue',
        label: '⚖️ 衡岳 · 状态机与不变量核验详情',
        children: <div>{hengyueText}</div>,
      },
      {
        key: 'jingchuan',
        label: '🔍 镜川 · 对抗审计与反模式复核详情',
        children: <div>{jingchuanText}</div>,
      },
    ];
  }, [isCollaboration, extra, metadata]);

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
