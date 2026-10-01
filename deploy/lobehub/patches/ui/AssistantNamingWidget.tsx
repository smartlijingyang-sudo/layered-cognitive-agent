'use client';

import { Button, Flexbox, Typography } from '@lobehub/ui';
import { Input } from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useMemo, useState } from 'react';

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    card: css`
      border: 1px solid ${cssVar.colorBorderSecondary};
      background: ${cssVar.colorBgElevated};
      border-radius: ${cssVar.borderRadiusLG};
      padding: 16px 20px;
      margin-top: 10px;
      margin-bottom: 10px;
      max-width: 520px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    `,
    title: css`
      font-weight: 600;
      font-size: 15px;
      margin-bottom: 6px;
      color: ${cssVar.colorText};
      display: flex;
      align-items: center;
      gap: 6px;
    `,
    subtitle: css`
      font-size: 13px;
      color: ${cssVar.colorTextSecondary};
      margin-bottom: 14px;
    `,
    candidateGrid: css`
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 12px;
    `,
    candidateChip: css`
      border-radius: 20px;
      padding: 6px 14px;
      height: auto;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      text-align: left;
    `,
    chipName: css`
      font-weight: 600;
      font-size: 13px;
    `,
    chipVibe: css`
      font-size: 11px;
      opacity: 0.8;
    `,
    customInputWrapper: css`
      margin-top: 8px;
      margin-bottom: 12px;
    `,
    previewBox: css`
      background: ${cssVar.colorFillTertiary};
      border-radius: ${cssVar.borderRadius};
      padding: 8px 12px;
      margin-bottom: 14px;
      font-size: 12px;
      color: ${cssVar.colorTextDescription};
    `,
    submitBtn: css`
      width: 100%;
      height: 38px;
      font-weight: 600;
    `,
    settledBanner: css`
      padding: 12px 16px;
      border-radius: ${cssVar.borderRadiusLG};
      background: ${cssVar.colorSuccessBg};
      border: 1px solid ${cssVar.colorSuccessBorder};
      color: ${cssVar.colorSuccessText};
      font-size: 13px;
      display: flex;
      align-items: center;
      gap: 8px;
      animation: fadeIn 0.3s ease-in-out;
    `,
    reactionCelebration: css`
      font-size: 20px;
      animation: bounce 0.6s ease infinite alternate;
    `,
  };
});

export interface NamingCandidate {
  name: string;
  vibe: string;
  rationale: string;
}

export interface AssistantNamingWidgetProps {
  embedToken?: string;
  assistantId?: string;
  candidates?: NamingCandidate[];
  allowCustom?: boolean;
  fixedChoice?: string;
  defaultCustomValue?: string;
  onSettled?: (name: string, vibe: string) => void;
}

export const AssistantNamingWidget = memo<AssistantNamingWidgetProps>(
  ({
    embedToken = '',
    assistantId = '',
    candidates = [
      { name: '星澜', vibe: '温柔敏锐', rationale: '如星光与波澜般清澈洞察' },
      { name: '破晓', vibe: '坚毅明晰', rationale: '如晨曦初升般果断可靠' },
    ],
    allowCustom = true,
    fixedChoice,
    defaultCustomValue = '',
    onSettled,
  }) => {
    const [selectedName, setSelectedName] = useState<string>(
      fixedChoice || (candidates.length > 0 ? candidates[0].name : '')
    );
    const [selectedVibe, setSelectedVibe] = useState<string>(
      fixedChoice ? '官方专属' : (candidates.length > 0 ? candidates[0].vibe : '')
    );
    const [customValue, setCustomValue] = useState<string>(defaultCustomValue);
    const [isCustom, setIsCustom] = useState<boolean>(false);
    const [submitting, setSubmitting] = useState<boolean>(false);
    const [settled, setSettled] = useState<boolean>(false);
    const [settledName, setSettledName] = useState<string>('');

    const activeName = useMemo(() => {
      if (fixedChoice) return fixedChoice;
      if (isCustom) return customValue.trim();
      return selectedName;
    }, [fixedChoice, isCustom, customValue, selectedName]);

    const activeVibe = useMemo(() => {
      if (fixedChoice) return '官方专属';
      if (isCustom) return '个性自拟';
      return selectedVibe;
    }, [fixedChoice, isCustom, selectedVibe]);

    const handleCandidateClick = useCallback((cand: NamingCandidate) => {
      setIsCustom(false);
      setSelectedName(cand.name);
      setSelectedVibe(cand.vibe);
    }, []);

    const handleCustomChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
      setCustomValue(e.target.value);
      setIsCustom(true);
    }, []);

    const handleConfirm = useCallback(async () => {
      if (!activeName || submitting || settled) return;
      setSubmitting(true);

      try {
        if (onSettled) {
          onSettled(activeName, activeVibe);
        }

        // Post to LCA settlement endpoint if embedToken or assistantId available
        if (assistantId || embedToken) {
          await fetch('/v1/onboarding/naming/settle', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              token: embedToken,
              assistant_id: assistantId,
              name: activeName,
              vibe: activeVibe,
            }),
          }).catch((err) => {
            console.warn('[AssistantNamingWidget] settle endpoint notify error:', err);
          });
        }

        setSettled(true);
        setSettledName(activeName);
      } catch (err) {
        console.error('[AssistantNamingWidget] failed to settle name:', err);
      } finally {
        setSubmitting(false);
      }
    }, [activeName, activeVibe, assistantId, embedToken, onSettled, settled, submitting]);

    if (settled) {
      return (
        <Flexbox className={styles.card}>
          <div className={styles.settledBanner}>
            <span className={styles.reactionCelebration}>🎉</span>
            <div>
              <strong>很高兴遇见你！</strong>
              <div>我是 {settledName}，专属身份已锚定，让我们开始并肩前行吧 ✨</div>
            </div>
          </div>
        </Flexbox>
      );
    }

    return (
      <Flexbox className={styles.card}>
        <div className={styles.title}>
          <span>为您设定专属助理身份与名称</span>
          <span>✨</span>
        </div>
        <div className={styles.subtitle}>
          点选下方灵感候选名或输入自拟称呼，完成专属命名仪式：
        </div>

        {/* 候选选项 */}
        <div className={styles.candidateGrid}>
          {fixedChoice ? (
            <Button
              type="primary"
              className={styles.candidateChip}
            >
              <span className={styles.chipName}>{fixedChoice}</span>
              <span className={styles.chipVibe}>官方固定项</span>
            </Button>
          ) : (
            candidates.map((cand) => {
              const isSelected = !isCustom && selectedName === cand.name;
              return (
                <Button
                  key={cand.name}
                  type={isSelected ? 'primary' : 'default'}
                  className={styles.candidateChip}
                  onClick={() => handleCandidateClick(cand)}
                  title={cand.rationale}
                >
                  <span className={styles.chipName}>{cand.name}</span>
                  <span className={styles.chipVibe}>{cand.vibe}</span>
                </Button>
              );
            })
          )}
        </div>

        {/* 自定义输入框 */}
        {allowCustom && !fixedChoice && (
          <div className={styles.customInputWrapper}>
            <Input
              placeholder="或者，输入你喜欢的自定义称呼..."
              value={customValue}
              onChange={handleCustomChange}
              onFocus={() => setIsCustom(true)}
              maxLength={20}
              allowClear
            />
          </div>
        )}

        {/* 实时动态预览 */}
        {activeName && (
          <div className={styles.previewBox}>
            💡 预览：「你好，我是 <strong>{activeName}</strong>（{activeVibe}），很高兴为你服务！」
          </div>
        )}

        {/* 确认按钮 */}
        <Button
          type="primary"
          className={styles.submitBtn}
          loading={submitting}
          disabled={!activeName}
          onClick={handleConfirm}
        >
          确定称呼并启程 ✨
        </Button>
      </Flexbox>
    );
  }
);

export default AssistantNamingWidget;
