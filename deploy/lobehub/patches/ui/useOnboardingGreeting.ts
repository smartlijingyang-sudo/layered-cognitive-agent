import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { messageService } from '@/services/message';
import { useChatStore } from '@/store/chat';
import { useUserStore } from '@/store/user';
import { userProfileSelectors } from '@/store/user/selectors';

import { buildOnboardingGreetingMessages } from './onboardingGreeting';

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
 *
 * The bubbles are created through the message service with a `createdAt` that
 * sorts before any existing message, so they always land at the TOP of the
 * conversation — even when the user typed their first message before the
 * welcome fetch resolved (previously they were appended to the latest-reply
 * slot at the bottom).
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
        if (!Array.isArray(data.messages) || data.messages.length === 0) return;

        const currentContext = contextRef.current;
        if (!currentContext.agentId) return;

        // Backdate the bubbles before any existing message so they stay pinned
        // at the top of the conversation (see onboardingGreeting.ts).
        const bubbles = buildOnboardingGreetingMessages(
          currentContext,
          messagesRef.current ?? [],
          data.messages,
        );

        const chatStore = useChatStore.getState();
        let parentId: string | undefined;

        for (let i = 0; i < bubbles.length; i++) {
          // Note: we do not cancel delivery mid-greeting for the same agent
          if (contextRef.current.agentId !== agentId) break;

          const bubble = bubbles[i];
          const created = await messageService.createMessage({
            agentId: currentContext.agentId,
            content: bubble.content,
            createdAt: bubble.createdAt,
            groupId: currentContext.groupId,
            parentId,
            role: 'assistant',
            threadId: currentContext.threadId,
            topicId: currentContext.topicId,
          } as any);

          if (created?.id) {
            parentId = created.id;
          }
          // Replace with the server-sorted list so the backdated greeting
          // renders at the top immediately (server orders by createdAt ASC).
          if (created?.messages) {
            chatStore.replaceMessages(created.messages, { context: currentContext });
          }

          if (i < bubbles.length - 1) {
            await new Promise((resolve) => setTimeout(resolve, 600));
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