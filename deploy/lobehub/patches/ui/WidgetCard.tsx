'use client';

import { Button, Flexbox, Typography } from '@lobehub/ui';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useState } from 'react';

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    card: css`
      border: 1px solid ${cssVar.colorBorderSecondary};
      background: ${cssVar.colorBgElevated};
      border-radius: ${cssVar.borderRadiusLG};
      padding: 12px 16px;
      margin-top: 8px;
      margin-bottom: 8px;
      max-width: 480px;
    `,
    title: css`
      font-weight: 600;
      font-size: 14px;
      margin-bottom: 10px;
      color: ${cssVar.colorText};
    `,
    optionGrid: css`
      display: flex;
      flex-direction: column;
      gap: 8px;
    `,
    selectedBadge: css`
      font-size: 12px;
      color: ${cssVar.colorSuccess};
      margin-top: 6px;
    `,
  };
});

export interface WidgetOption {
  id: string;
  label: string;
  description?: string;
}

interface WidgetCardProps {
  runId?: string;
  messageId?: string;
  content?: string;
  options?: WidgetOption[];
  onSelectOption?: (option: WidgetOption) => void;
}

export const WidgetCard = memo<WidgetCardProps>(
  ({ runId, messageId, content = '请选择下一步操作：', options = [], onSelectOption }) => {
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);

    const handleSelect = useCallback(
      async (option: WidgetOption) => {
        if (selectedId || submitting) return;
        setSelectedId(option.id);
        setSubmitting(true);

        try {
          if (onSelectOption) {
            onSelectOption(option);
          } else if (runId) {
            await fetch(`/lca-api/runs/${runId}/answer`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                approval_id: 'widget',
                idempotency_key: `${runId}:${messageId || 'widget'}`,
                payload: option.label || option.id,
              }),
            });
          }
        } catch (err) {
          console.error('[WidgetCard] failed to submit option answer', err);
        } finally {
          setSubmitting(false);
        }
      },
      [runId, messageId, selectedId, submitting, onSelectOption],
    );

    if (!options || options.length === 0) {
      return null;
    }

    return (
      <Flexbox className={styles.card}>
        <Typography.Text className={styles.title}>{content}</Typography.Text>
        <div className={styles.optionGrid}>
          {options.map((opt) => (
            <Button
              key={opt.id}
              block
              disabled={Boolean(selectedId && selectedId !== opt.id)}
              loading={submitting && selectedId === opt.id}
              onClick={() => handleSelect(opt)}
              type={selectedId === opt.id ? 'primary' : 'default'}
            >
              {opt.label}
            </Button>
          ))}
        </div>
        {selectedId && (
          <span className={styles.selectedBadge}>
            ✓ 已选择: {options.find((o) => o.id === selectedId)?.label || selectedId}
          </span>
        )}
      </Flexbox>
    );
  },
);

export default WidgetCard;
