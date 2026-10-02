'use client';

import { Button, Empty, Tag, Typography, message } from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useEffect, useState } from 'react';

const { Text, Title } = Typography;

export interface AvatarVariantPayload {
  size: string;
  url: string;
}

export interface AvatarCandidatePayload {
  candidate_id: string;
  prompt?: string;
  variants: AvatarVariantPayload[];
}

export interface GeneratedCandidate {
  id: string;
  imageUrl?: string;
  prompt?: string;
}

export interface AssistantAvatarWidgetProps {
  /** 助理唯一标识 */
  assistantId?: string;
  /** 形象主题 (如 dino / animals) */
  theme?: string;
  /** 自定义类名 */
  className?: string;
  /** 自定义样式 */
  style?: React.CSSProperties;
}

const CANDIDATES_ENDPOINT = (assistantId: string) =>
  `/lca-api/v1/assistants/${assistantId}/avatar/candidates`;

const SET_ENDPOINT = (assistantId: string) =>
  `/lca-api/v1/assistants/${assistantId}/avatar/set`;

function authHeaders(): Record<string, string> {
  const envToken =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env
          ?.NEXT_PUBLIC_LCA_TOKEN
      : undefined;
  const token = envToken || 'lca-local';
  const mockDevUserId =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env
          ?.NEXT_PUBLIC_MOCK_DEV_USER_ID
      : undefined;
  const userId =
    (typeof window !== 'undefined' &&
      (window as { __LCA_USER_ID?: string } | undefined)?.__LCA_USER_ID) ||
    mockDevUserId ||
    'local-dev-user';
  return {
    Authorization: `Bearer ${token}`,
    'x-lca-token': token,
    'x-lca-user-id': userId,
  };
}

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
    candidateImage: css`
      width: 96px;
      height: 96px;
      object-fit: cover;
      border-radius: 12px;
      border: 1px solid ${cssVar.colorBorderSecondary};
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
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    `,
    emptyState: css`
      padding: 24px 8px;
      text-align: center;
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
 * 候选来自生成式管线（GET /v1/assistants/{id}/avatar/candidates），确认后调用
 * POST /v1/assistants/{id}/avatar/set 激活。成功即清空候选池（服务端同步清空）
 * 并广播 ``lca-assistant-avatar-changed``，失败则保留候选并给出警告。
 */
export const AssistantAvatarWidget = memo<AssistantAvatarWidgetProps>(
  ({ assistantId, className, style }) => {
    const [candidates, setCandidates] = useState<GeneratedCandidate[]>([]);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [confirmed, setConfirmed] = useState(false);

    const effectiveId = assistantId || 'default';

    const loadCandidates = useCallback(async () => {
      setLoading(true);
      try {
        const res = await fetch(CANDIDATES_ENDPOINT(effectiveId), { headers: authHeaders() });
        if (!res.ok) {
          setCandidates([]);
          return;
        }
        const data = await res.json();
        const list: GeneratedCandidate[] = (data.candidates || []).map(
          (c: AvatarCandidatePayload) => ({
            id: c.candidate_id,
            imageUrl: c.variants.find((v) => v.size === 'medium')?.url || c.variants[0]?.url,
            prompt: c.prompt,
          }),
        );
        setCandidates(list);
        setSelectedId((prev) =>
          prev && list.some((c) => c.id === prev) ? prev : list[0]?.id || null,
        );
      } catch {
        setCandidates([]);
      } finally {
        setLoading(false);
      }
    }, [effectiveId]);

    useEffect(() => {
      setConfirmed(false);
      void loadCandidates();
    }, [loadCandidates]);

    // 确认换装：POST /avatar/set 激活候选；成功后清空候选池并广播事件。
    const handleConfirm = useCallback(async () => {
      if (!selectedId) return;
      setLoading(true);
      try {
        const res = await fetch(SET_ENDPOINT(effectiveId), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({ candidate_id: selectedId }),
        });
        if (!res.ok) {
          message.warning('形象激活失败，请稍后重试');
          return;
        }
        setConfirmed(true);
        setCandidates([]);
        setSelectedId(null);
        message.success('我的头像换好了 🎉');
        if (typeof window !== 'undefined') {
          window.dispatchEvent(
            new CustomEvent('lca-assistant-avatar-changed', {
              detail: { assistant_id: effectiveId, candidate_id: selectedId },
            }),
          );
        }
      } catch {
        message.warning('形象激活失败，请稍后重试');
      } finally {
        setLoading(false);
      }
    }, [effectiveId, selectedId]);

    const selected = candidates.find((c) => c.id === selectedId) || null;

    return (
      <div className={`${styles.container} ${className || ''}`} style={style}>
        <div className={styles.header}>
          <div className={styles.titleRow}>
            <Title level={5} style={{ margin: 0 }}>
              🎨 挑选助理新形象
            </Title>
            <Tag color="purple">AI 生成</Tag>
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            选择后点击确认即可全局生效
          </Text>
        </div>

        {loading && candidates.length === 0 ? (
          <div className={styles.emptyState}>
            <Text type="secondary">加载候选形象中...</Text>
          </div>
        ) : candidates.length === 0 ? (
          <div className={styles.emptyState}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="先让助理生成几个新形象吧"
            />
          </div>
        ) : (
          <>
            <div className={styles.grid}>
              {candidates.map((cand) => {
                const isSelected = selectedId === cand.id;
                return (
                  <div
                    key={cand.id}
                    className={`${styles.candidateCard} ${isSelected ? 'selected' : ''}`}
                    onClick={() => !confirmed && setSelectedId(cand.id)}
                  >
                    <div className={styles.avatarWrapper}>
                      {cand.imageUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={cand.imageUrl}
                          alt={cand.prompt || cand.id}
                          className={styles.candidateImage}
                        />
                      ) : (
                        <Text type="secondary" style={{ fontSize: 32 }}>
                          🖼️
                        </Text>
                      )}
                    </div>
                    <div className={styles.cardTitle}>
                      <span>{cand.prompt ? cand.prompt.slice(0, 12) : '新形象'}</span>
                      <Tag color={isSelected ? 'blue' : 'default'} style={{ fontSize: 10, margin: 0 }}>
                        {isSelected ? '已选中' : '候选'}
                      </Tag>
                    </div>
                    {cand.prompt && <div className={styles.cardDesc}>{cand.prompt}</div>}
                  </div>
                );
              })}
            </div>

            <div className={styles.footer}>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  当前选中：
                  <strong>{selected?.prompt || selectedId || '未选择'}</strong>
                </Text>
              </div>
              <Button
                type="primary"
                size="small"
                loading={loading}
                disabled={!selectedId}
                onClick={handleConfirm}
              >
                确认使用此形象
              </Button>
            </div>
          </>
        )}

        {confirmed && (
          <div className={styles.footer}>
            <Text type="success" style={{ fontSize: 12, fontWeight: 500 }}>
              ✓ 新形象已生效
            </Text>
            <Button size="small" type="default" disabled>
              ✓ 已生效
            </Button>
          </div>
        )}
      </div>
    );
  },
);

AssistantAvatarWidget.displayName = 'AssistantAvatarWidget';

export default AssistantAvatarWidget;