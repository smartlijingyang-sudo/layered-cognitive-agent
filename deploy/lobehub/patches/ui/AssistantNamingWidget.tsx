'use client';

import { Button, Flexbox } from '@lobehub/ui';
import { Input } from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

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
  allowCustom?: boolean;
  assistantId?: string;
  candidates?: NamingCandidate[];
  defaultCustomValue?: string;
  embedToken?: string;
  fixedChoice?: string;
  onSettled?: (name: string, vibe: string) => void;
}

export const AssistantNamingWidget = memo<AssistantNamingWidgetProps>(
  ({
    embedToken = '',
    assistantId = '',
    candidates: propCandidates,
    allowCustom = true,
    fixedChoice,
    defaultCustomValue = '',
    onSettled,
  }) => {
    const { i18n } = useTranslation();
    const isZh = (i18n.language || '').toLowerCase().startsWith('zh');

    const defaultCandidates: NamingCandidate[] = useMemo(() => {
      if (propCandidates && propCandidates.length > 0) {
        return propCandidates;
      }
      return isZh
        ? [
            { name: '星澜', rationale: '如星光与波澜般清澈洞察', vibe: '温柔敏锐' },
            { name: '破晓', rationale: '如晨曦初升般果断可靠', vibe: '坚毅明晰' },
          ]
        : [
            { name: 'Athena', rationale: 'Wise and resolute personal companion', vibe: 'Sharp & Focused' },
            { name: 'Nova', rationale: 'Clear insight and steadfast execution', vibe: 'Calm & Thorough' },
          ];
    }, [propCandidates, isZh]);

    const [selectedName, setSelectedName] = useState<string>(
      fixedChoice || (defaultCandidates.length > 0 ? defaultCandidates[0].name : '')
    );
    const [selectedVibe, setSelectedVibe] = useState<string>(
      fixedChoice
        ? (isZh ? '官方专属' : 'Default')
        : (defaultCandidates.length > 0 ? defaultCandidates[0].vibe : '')
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
      if (fixedChoice) return isZh ? '官方专属' : 'Default';
      if (isCustom) return isZh ? '个性自拟' : 'Custom';
      return selectedVibe;
    }, [fixedChoice, isCustom, selectedVibe, isZh]);

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

        const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        const userId =
          (typeof window !== 'undefined' && (window as any)?.__LCA_USER_ID) ||
          process.env.NEXT_PUBLIC_MOCK_DEV_USER_ID ||
          'local-dev-user';

        // Post to LCA settlement endpoint if embedToken or assistantId available
        if (assistantId || embedToken) {
          await fetch('/lca-api/v1/onboarding/naming/settle', {
            body: JSON.stringify({
              assistant_id: assistantId,
              name: activeName,
              token: embedToken,
              vibe: activeVibe,
            }),
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
              'x-lca-token': token,
              'x-lca-user-id': userId,
            },
            method: 'POST',
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
              <strong>{isZh ? '很高兴遇见你！' : 'Nice to meet you!'}</strong>
              <div>
                {isZh
                  ? `我是 ${settledName}，专属身份已锚定，让我们开始并肩前行吧 ✨`
                  : `I'm ${settledName}. My personal identity is set, let's take things off your plate! ✨`}
              </div>
            </div>
          </div>
        </Flexbox>
      );
    }

    return (
      <Flexbox className={styles.card}>
        <div className={styles.title}>
          <span>{isZh ? '为您设定专属助理身份与名称' : 'Name Your Personal Agent'}</span>
          <span>✨</span>
        </div>
        <div className={styles.subtitle}>
          {isZh
            ? '点选下方灵感候选名或输入自拟称呼，完成专属命名仪式：'
            : 'Choose a name below or enter your own to complete the naming ceremony:'}
        </div>

        {/* Candidate Chips */}
        <div className={styles.candidateGrid}>
          {fixedChoice ? (
            <Button
              className={styles.candidateChip}
              type="primary"
            >
              <span className={styles.chipName}>{fixedChoice}</span>
              <span className={styles.chipVibe}>{isZh ? '官方固定项' : 'Default'}</span>
            </Button>
          ) : (
            defaultCandidates.map((cand) => {
              const isSelected = !isCustom && selectedName === cand.name;
              return (
                <Button
                  className={styles.candidateChip}
                  key={cand.name}
                  onClick={() => handleCandidateClick(cand)}
                  title={cand.rationale}
                  type={isSelected ? 'primary' : 'default'}
                >
                  <span className={styles.chipName}>{cand.name}</span>
                  <span className={styles.chipVibe}>{cand.vibe}</span>
                </Button>
              );
            })
          )}
        </div>

        {/* Custom Input */}
        {allowCustom && !fixedChoice && (
          <div className={styles.customInputWrapper}>
            <Input
              allowClear
              maxLength={20}
              onChange={handleCustomChange}
              onFocus={() => setIsCustom(true)}
              placeholder={isZh ? '或者，输入你喜欢的自定义称呼...' : 'Or enter a custom name...'}
              value={customValue}
            />
          </div>
        )}

        {/* Live Preview */}
        {activeName && (
          <div className={styles.previewBox}>
            {isZh
              ? <>💡 预览：「你好，我是 <strong>{activeName}</strong>（{activeVibe}），很高兴为你服务！」</>
              : <>💡 Preview: "Hey, I'm <strong>{activeName}</strong> ({activeVibe}), ready to help!"</>}
          </div>
        )}

        {/* Confirm Button */}
        <Button
          className={styles.submitBtn}
          disabled={!activeName}
          loading={submitting}
          onClick={handleConfirm}
          type="primary"
        >
          {isZh ? '确定称呼并启程 ✨' : 'Confirm Name & Get Started ✨'}
        </Button>
      </Flexbox>
    );
  }
);

AssistantNamingWidget.displayName = 'AssistantNamingWidget';

export default AssistantNamingWidget;
