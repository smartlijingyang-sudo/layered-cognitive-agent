import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { useChatStore } from '@/store/chat';
import { useUserStore } from '@/store/user';
import { userProfileSelectors } from '@/store/user/selectors';

export interface ConversationContextLike {
  agentId?: string;
  groupId?: string;
  threadId?: string;
  topicId?: string;
}

/**
 * useOnboardingGreeting
 *
 * Proactively triggers Muse-style onboarding opening messages when a user
 * enters an agent conversation with an empty chat history.
 */
export const useOnboardingGreeting = (
  context: ConversationContextLike,
  messages: any[] | undefined,
) => {
  const { i18n } = useTranslation();
  const userId = useUserStore(userProfileSelectors.userId);
  const greetingInFlightRef = useRef<string | null>(null);

  // Keep latest context and messages in refs to avoid useEffect cancellations when messages update
  const contextRef = useRef(context);
  contextRef.current = context;

  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  useEffect(() => {
    const agentId = context.agentId;
    // Only proceed when an agent is bound and messages is an initialized empty array
    if (!agentId || !Array.isArray(messages) || messages.length > 0) {
      return;
    }

    const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
    const effectiveUserId =
      userId ||
      (typeof window !== 'undefined' && (window as any)?.__LCA_USER_ID) ||
      process.env.NEXT_PUBLIC_MOCK_DEV_USER_ID ||
      'local-dev-user';

    const storageKey = `lca_greeted_${effectiveUserId}_${agentId}`;
    if (typeof window !== 'undefined' && window.localStorage?.getItem(storageKey)) {
      return;
    }

    if (greetingInFlightRef.current === agentId) {
      return;
    }
    greetingInFlightRef.current = agentId;

    let cancelled = false;

    const runGreeting = async () => {
      try {
        const rawLocale = (i18n.language || (typeof window !== 'undefined' && window.navigator?.language) || 'en').toLowerCase();
        const locale = rawLocale.startsWith('zh') ? 'zh' : 'en';

        const url = `/lca-api/v1/onboarding/welcome?locale=${encodeURIComponent(locale)}&assistant_id=${encodeURIComponent(agentId)}`;
        const res = await fetch(url, {
          headers: {
            Authorization: `Bearer ${token}`,
            'x-lca-token': token,
            'x-lca-user-id': effectiveUserId,
          },
        });

        if (!res.ok || cancelled) return;
        const data = await res.json();

        // Mark as greeted in localStorage across sessions / tabs
        if (typeof window !== 'undefined' && window.localStorage) {
          window.localStorage.setItem(storageKey, '1');
        }

        if (cancelled) return;

        if (Array.isArray(data.messages) && data.messages.length > 0) {
          const optimisticCreateMessage = useChatStore.getState().optimisticCreateMessage;
          let parentId: string | undefined = undefined;

          for (let i = 0; i < data.messages.length; i++) {
            // Note: we do not cancel delivery mid-greeting for the same agent
            if (contextRef.current.agentId !== agentId) break;
            const content = data.messages[i];
            const currentContext = contextRef.current;
            const created = await optimisticCreateMessage({
              agentId: currentContext.agentId,
              content,
              groupId: currentContext.groupId,
              parentId,
              role: 'assistant',
              threadId: currentContext.threadId,
              topicId: currentContext.topicId,
            });
            if (created?.id) {
              parentId = created.id;
            }
            if (i < data.messages.length - 1) {
              await new Promise((resolve) => setTimeout(resolve, 600));
            }
          }
        }
      } catch (err) {
        console.warn('[useOnboardingGreeting] failed to trigger proactive welcome:', err);
      } finally {
        if (greetingInFlightRef.current === agentId) {
          greetingInFlightRef.current = null;
        }
      }
    };

    runGreeting();

    return () => {
      // Only mark cancelled if switching away from this agent
      if (contextRef.current.agentId !== agentId) {
        cancelled = true;
      }
    };
  }, [context.agentId, context.topicId, context.threadId, context.groupId, !messages || messages.length === 0, userId, i18n.language]);
};

export default useOnboardingGreeting;
