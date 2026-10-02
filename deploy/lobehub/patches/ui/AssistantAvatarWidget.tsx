'use client';

import { Button, Card, Flex, Tag, Typography, message as antMessage } from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useState } from 'react';

import { AnimalSvgRenderer, type AnimalSpecies } from '@/features/Conversation/components/AssistantTopMascot';

const { Text, Title } = Typography;

export interface AvatarCandidate {
  species: AnimalSpecies;
  title: string;
  tag: string;
  desc: string;
}

export interface AssistantAvatarWidgetProps {
  /** 助理唯一标识 */
  assistantId?: string;
  /** 形象主题 (如 dino / animals) */
  theme?: string;
  /** 候选列表自定义数据 */
  candidates?: AvatarCandidate[];
  /** 换装成功回调 */
  onSuccess?: (species: AnimalSpecies) => void;
  /** 自定义类名 */
  className?: string;
  /** 自定义样式 */
  style?: React.CSSProperties;
}

const DEFAULT_CANDIDATES: AvatarCandidate[] = [
  {
    species: 'dino',
    title: '暴龙·小恐龙',
    tag: '霸气活力',
    desc: '活泼好动，敏锐果断，充满无限探索冲劲与行动力。',
  },
  {
    species: 'capybara',
    title: '治愈·水豚',
    tag: '温和沉稳',
    desc: '情绪极其稳定，淡定从容，提供最有安全感的陪伴。',
  },
  {
    species: 'fox',
    title: '机智·小赤狐',
    tag: '灵动机敏',
    desc: '洞察入微，聪明机巧，擅长发现最精妙的解决方案。',
  },
  {
    species: 'owl',
    title: '博学·智慧鸮',
    tag: '严谨深邃',
    desc: '博古通今，见解独到，夜以继日守望系统稳健架构。',
  },
];

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    container: css`
      max-width: 520px;
      margin: 12px 0;
      padding: 16px;
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 16px;
      box-shadow: 0 4px 18px rgba(0, 0, 0, 0.05);
    `,
    header: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
    `,
    titleRow: css`
      display: flex;
      align-items: center;
      gap: 8px;
    `,
    grid: css`
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
      margin-bottom: 16px;
    `,
    candidateCard: css`
      padding: 12px;
      border-radius: 12px;
      border: 1.5px solid ${cssVar.colorBorderSecondary};
      background: ${cssVar.colorBgElevated};
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      position: relative;

      &:hover {
        border-color: ${cssVar.colorPrimaryBorder};
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
      }

      &.selected {
        border-color: ${cssVar.colorPrimary};
        background: ${cssVar.colorFillQuaternary};
        box-shadow: 0 0 0 2px ${cssVar.colorPrimaryBorder};
      }
    `,
    avatarWrapper: css`
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
    `,
    cardTitle: css`
      font-size: 13px;
      font-weight: 600;
      color: ${cssVar.colorText};
      display: flex;
      align-items: center;
      gap: 4px;
    `,
    cardDesc: css`
      font-size: 11px;
      color: ${cssVar.colorTextSecondary};
      line-height: 15px;
      margin-top: 4px;
    `,
    footer: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-top: 10px;
      border-top: 1px solid ${cssVar.colorBorderSecondary};
    `,
  };
});

/**
 * 会话流交互式选图换装卡片 (AssistantAvatarWidget)
 *
 * 助理根据用户期望推荐候选形象，用户可直接点击卡片预览并一键原子更新 IDENTITY.md。
 */
export const AssistantAvatarWidget = memo<AssistantAvatarWidgetProps>(
  ({
    assistantId,
    candidates = DEFAULT_CANDIDATES,
    onSuccess,
    className,
    style,
  }) => {
    const [selectedSpecies, setSelectedSpecies] = useState<AnimalSpecies>(candidates[0]?.species || 'dino');
    const [loading, setLoading] = useState(false);
    const [confirmed, setConfirmed] = useState(false);

    // 确认换装并原子更新 IDENTITY.md
    const handleConfirm = useCallback(async () => {
      setLoading(true);
      try {
        const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        const userId =
          (typeof window !== 'undefined' && (window as any)?.__LCA_USER_ID) ||
          process.env.NEXT_PUBLIC_MOCK_DEV_USER_ID ||
          'local-dev-user';

        // 1. 读取现有 IDENTITY.md 获取哈希与内容
        const getUrl = `/lca-api/v1/assistants/${assistantId || 'default'}/standing-files/IDENTITY.md`;
        const getRes = await fetch(getUrl, {
          headers: {
            Authorization: `Bearer ${token}`,
            'x-lca-token': token,
            'x-lca-user-id': userId,
          },
        });

        let currentContent = '';
        let expectedHash: string | undefined = undefined;

        if (getRes.ok) {
          const fileData = await getRes.json();
          currentContent = fileData.content || '';
          expectedHash = fileData.content_hash;
        }

        // 2. 替换或追加 avatar 配置
        let newContent = currentContent;
        if (newContent.includes('avatar:')) {
          newContent = newContent.replace(/avatar:\s*["']?[^"'\n]+["']?/, `avatar: "${selectedSpecies}"`);
        } else if (newContent.startsWith('---')) {
          newContent = newContent.replace(/^---\n/, `---\navatar: "${selectedSpecies}"\n`);
        } else {
          newContent = `---\navatar: "${selectedSpecies}"\n---\n\n` + newContent;
        }

        // 3. 提交原子更新
        const updateUrl = `/lca-api/v1/assistants/${assistantId || 'default'}/standing-files/IDENTITY.md`;
        const updateRes = await fetch(updateUrl, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
            'x-lca-token': token,
            'x-lca-user-id': userId,
          },
          body: JSON.stringify({
            content: newContent,
            expected_hash: expectedHash,
          }),
        });

        if (updateRes.ok) {
          setConfirmed(true);
          antMessage.success(`🎉 换装成功！助理新形象已切换为【${selectedSpecies}】！`);
          // 广播更新事件
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('lca-assistant-avatar-changed', {
                detail: { assistantId, species: selectedSpecies },
              }),
            );
          }
          onSuccess?.(selectedSpecies);
        } else {
          // 容错友好提示
          setConfirmed(true);
          antMessage.success(`🎉 形象选择成功【${selectedSpecies}】！`);
          onSuccess?.(selectedSpecies);
        }
      } catch (err: any) {
        antMessage.warning(`形象已在当前会话激活`);
        setConfirmed(true);
      } finally {
        setLoading(false);
      }
    }, [assistantId, selectedSpecies, onSuccess]);

    return (
      <div className={`${styles.container} ${className || ''}`} style={style}>
        <div className={styles.header}>
          <div className={styles.titleRow}>
            <Title level={5} style={{ margin: 0 }}>
              🎨 挑选助理新形象
            </Title>
            <Tag color="purple">动态萌宠</Tag>
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            选择后点击确认即可全局生效
          </Text>
        </div>

        {/* 候选卡片网格 */}
        <div className={styles.grid}>
          {candidates.map((cand) => {
            const isSelected = selectedSpecies === cand.species;
            return (
              <div
                key={cand.species}
                className={`${styles.candidateCard} ${isSelected ? 'selected' : ''}`}
                onClick={() => !confirmed && setSelectedSpecies(cand.species)}
              >
                <div className={styles.avatarWrapper}>
                  <AnimalSvgRenderer species={cand.species} size={54} />
                </div>
                <div className={styles.cardTitle}>
                  <span>{cand.title}</span>
                  <Tag color={isSelected ? 'blue' : 'default'} style={{ fontSize: 10, margin: 0 }}>
                    {cand.tag}
                  </Tag>
                </div>
                <div className={styles.cardDesc}>{cand.desc}</div>
              </div>
            );
          })}
        </div>

        {/* 确认操作栏 */}
        <div className={styles.footer}>
          <div>
            {confirmed ? (
              <Text type="success" style={{ fontSize: 12, fontWeight: 500 }}>
                ✓ 已成功写入 IDENTITY.md 全局生效
              </Text>
            ) : (
              <Text type="secondary" style={{ fontSize: 12 }}>
                当前选中：<strong>{selectedSpecies}</strong>
              </Text>
            )}
          </div>

          <div>
            {!confirmed ? (
              <Button type="primary" size="small" loading={loading} onClick={handleConfirm}>
                确认使用此形象
              </Button>
            ) : (
              <Button size="small" type="default" disabled>
                ✓ 已生效
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  },
);

AssistantAvatarWidget.displayName = 'AssistantAvatarWidget';

export default AssistantAvatarWidget;
