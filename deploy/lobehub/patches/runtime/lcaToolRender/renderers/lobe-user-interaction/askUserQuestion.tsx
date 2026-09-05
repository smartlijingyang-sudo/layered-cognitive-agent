'use client';

/**
 * LCA `askUserQuestion` renderer.
 *
 * LCA runs suspend server-side when the model calls `askUserQuestion`
 * (the tool raises ApprovalPendingError → run status `waiting_input`, the
 * live tail stays open). LobeHub's own interaction surface is coupled to its
 * client agent runtime and cannot resume an LCA run, so LCA owns the resume
 * path: this card renders the question(s) with the shared ask-user components
 * and POSTs the answer to `/lca-api/runs/<run_id>/answer`. The run then
 * resumes on the same live stream that LcaRunDriver keeps consuming.
 *
 * Contract with LcaRunDriver (SSOT: patches/runtime/LcaRunDriver.ts):
 *   - `args.questions`            → the model's questions (ARG_KEYS includes
 *                                   `questions`, so they survive pickArgs).
 *   - `pluginState.lca`           → `{ run_id, status: 'waiting_input' }`,
 *                                   written by the driver when the tool
 *                                   suspends the run. Present ⇔ interactive.
 *   - `pluginState.askUserAnswers`→ structured answers, written here after a
 *                                   successful POST /answer; present ⇔ the
 *                                   read-only result view is shown.
 */

import type {
  AskUserDraft,
  AskUserQuestionArgs,
  AskUserQuestionItem,
} from '@lobechat/shared-tool-ui/ask-user';
import {
  AskUserQuestionResult,
  AskUserQuestionView,
  DRAFT_PLUGIN_STATE_KEY,
  FREEFORM_PAYLOAD_KEY,
  normalizeAskUserQuestions,
  resolveAskUserAnswers,
  useAskUserForm,
} from '@lobechat/shared-tool-ui/ask-user';
import type { BuiltinRenderProps } from '@lobechat/types';
import { memo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useChatStore } from '@/store/chat';

const LCA_TOKEN = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';

type LcaState = Record<string, unknown>;

interface LcaWaitContext {
  run_id?: string;
  status?: string;
}

type InteractionAction =
  | { payload: Record<string, unknown>; type: 'submit' }
  | { payload?: Record<string, unknown>; reason?: string; type: 'skip' }
  | { payload?: Record<string, unknown>; type: 'cancel' };

/**
 * Serialize the structured answers into the human-readable text the backend
 * feeds back to the model (`HumanAnswerResumeInputAdapter` passes the payload
 * through verbatim as the human answer).
 */
const buildAnswerText = (
  questions: AskUserQuestionItem[],
  payload: Record<string, unknown>,
): string => {
  const freeform = payload[FREEFORM_PAYLOAD_KEY];
  if (typeof freeform === 'string' && freeform.trim()) return freeform.trim();

  const lines: string[] = [];
  for (const question of questions) {
    const answer = payload[question.question];
    if (answer == null) continue;
    const text = Array.isArray(answer) ? answer.join(', ') : String(answer);
    if (text) lines.push(`${question.question} ${text}`);
  }
  return lines.length > 0 ? lines.join('\n') : JSON.stringify(payload);
};

const askUserQuestion = memo<
  BuiltinRenderProps<AskUserQuestionArgs, LcaState, string>
>((props) => {
  const { args, content, messageId, pluginError, pluginState, toolCallId } = props;
  const { t } = useTranslation('tool');
  const { t: tPlugin } = useTranslation('plugin');

  const questions = normalizeAskUserQuestions(args);
  const answers = resolveAskUserAnswers(
    pluginState as { askUserAnswers?: Record<string, string | string[]> } | undefined,
    content,
  );
  const lca = (pluginState?.lca ?? undefined) as LcaWaitContext | undefined;
  const runId = typeof lca?.run_id === 'string' ? lca.run_id : '';
  const pending = !answers && !!runId && lca?.status === 'waiting_input';

  const setInterventionDraft = useChatStore((s) => s.setInterventionDraft);
  const setInterventionAnswers = useChatStore((s) => s.setInterventionAnswers);

  const submitAnswer = useCallback(
    async (answerText: string) => {
      const res = await fetch(`/lca-api/runs/${runId}/answer`, {
        body: JSON.stringify({
          approval_id: toolCallId || 'askUserQuestion',
          idempotency_key: `${runId}:${toolCallId || messageId}`,
          payload: answerText,
        }),
        headers: {
          Authorization: `Bearer ${LCA_TOKEN}`,
          'Content-Type': 'application/json',
        },
        method: 'POST',
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`answer HTTP ${res.status}: ${text.slice(0, 200)}`);
      }
    },
    [messageId, runId, toolCallId],
  );

  const onInteractionAction = useCallback(
    async (action: InteractionAction) => {
      if (!runId || action.type === 'cancel') return;
      const payload =
        action.type === 'skip'
          ? { [FREEFORM_PAYLOAD_KEY]: t('askUserQuestion.skip') }
          : (action.payload ?? {});
      await submitAnswer(buildAnswerText(questions, payload));
      await setInterventionAnswers(messageId, payload);
    },
    [messageId, questions, runId, setInterventionAnswers, submitAnswer, t],
  );

  const persistedDraft = pluginState?.[DRAFT_PLUGIN_STATE_KEY];
  const writeDraft = useCallback(
    (draft: AskUserDraft) => setInterventionDraft(messageId, draft),
    [messageId, setInterventionDraft],
  );

  const form = useAskUserForm({
    args,
    onInteractionAction,
    persistedDraft,
    writeDraft,
  });

  // Answered, or no live run context (e.g. historical / reloaded message):
  // read-only summary of what was asked and what was picked.
  if (!pending) {
    return (
      <AskUserQuestionResult
        answers={answers}
        isError={!!pluginError && !answers}
        labels={{
          noAnswer: tPlugin('builtins.lobe-claude-code.askUserQuestion.noAnswer'),
          notAnswered: tPlugin('builtins.lobe-claude-code.askUserQuestion.notAnswered'),
        }}
        questions={questions}
      />
    );
  }

  return (
    <AskUserQuestionView
      {...form}
      labels={{
        customPlaceholder: t('askUserQuestion.customOption.placeholder'),
        escapeBack: t('askUserQuestion.escape.back'),
        escapeEnter: t('askUserQuestion.escape.enter'),
        escapePlaceholder: t('askUserQuestion.escape.placeholder'),
        multiSelectTag: t('askUserQuestion.multiSelectTag'),
        skip: t('askUserQuestion.skip'),
        submit: t('askUserQuestion.submit'),
        timeExpired: '',
        timeRemaining: () => '',
      }}
      showCountdown={false}
    />
  );
});

askUserQuestion.displayName = 'askUserQuestion';

export { askUserQuestion };
export default askUserQuestion;
