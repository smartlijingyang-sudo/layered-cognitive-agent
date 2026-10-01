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

  useEffect(() => {
    const agentId = context.agentId;
    // Only proceed when an agent is bound and messages is an initialized empty array
    if (!agentId || !Array.isArray(messages) || messages.length > 0) {
      return;
    }

    const storageKey = `lca_greeted_${userId || 'anon'}_${agentId}`;
    if (typeof window !== 'undefined' && window.sessionStorage?.getItem(storageKey)) {
      return;
    }

    if (greetingInFlightRef.current === agentId) {
      return;
    }
    greetingInFlightRef.current = agentId;

    let cancelled = false;

    const runGreeting = async () => {
      try {
        const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        const effectiveUserId =
          userId ||
          (typeof window !== 'undefined' && (window as any)?.__LCA_USER_ID) ||
          process.env.NEXT_PUBLIC_MOCK_DEV_USER_ID ||
          'local-dev-user';

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

        if (typeof window !== 'undefined' && window.sessionStorage) {
          window.sessionStorage.setItem(storageKey, '1');
        }

        if (cancelled) return;

        if (Array.isArray(data.messages) && data.messages.length > 0) {
          const optimisticCreateMessage = useChatStore.getState().optimisticCreateMessage;
          let parentId: string | undefined = undefined;

          for (let i = 0; i < data.messages.length; i++) {
            if (cancelled) break;
            const content = data.messages[i];
            const created = await optimisticCreateMessage({
              agentId: context.agentId,
              content,
              groupId: context.groupId,
              parentId,
              role: 'assistant',
              threadId: context.threadId,
              topicId: context.topicId,
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
      cancelled = true;
    };
  }, [context.agentId, context.topicId, context.threadId, context.groupId, messages, userId, i18n.language]);
};

export default useOnboardingGreeting;
