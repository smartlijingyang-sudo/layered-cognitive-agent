// LCA-P1: in-memory message snapshot reader for the LCA gateway path.
//
// The native gateway path reloads the conversation from the DB at every
// reconciliation point (`fetchAndReplaceMessages` on `stream_start`,
// `tool_end`, `step_complete`, `agent_runtime_end`). LCA persists the
// assistant row only when the turn seals, so mid-run those rows are hollow
// and a refetch overwrites the content the stream already rendered. This
// reader answers the same query from `dbMessagesMap` — the raw bucket the
// handler itself writes through `internal_dispatchMessage` /
// `replaceMessages` (the same surface `dbMessageSelectors.getDbMessageById`
// walks) — so a mid-run reload returns what is already on screen instead of
// the DB's stale view.
//
// The returned array is the live store array, not a copy: feeding it straight
// back into `replaceMessages` hits that action's `isEqual` early-return, which
// is what keeps a mid-run reload from re-rendering the conversation.

import type { ConversationContext, UIChatMessage } from '@lobechat/types';

import { dbMessageSelectors } from '@/store/chat/slices/message/selectors/dbMessage';
import type { ChatStore } from '@/store/chat/store';
import { messageMapKey } from '@/store/chat/utils/messageMapKey';

/** Query shape accepted by the reader; mirrors `messageService.getMessages`. */
export type LcaMessagesQuery = ConversationContext & { skipWorks?: boolean };

/** Reader contract the LCA event handler reconciles against. */
export type LcaMessagesReader = (query: LcaMessagesQuery) => Promise<UIChatMessage[]>;

export const createLcaInMemoryMessagesReader = (get: () => ChatStore): LcaMessagesReader => {
  return async (query) => {
    const state = get();

    // Key the bucket exactly the way `replaceMessages` keys its write — same
    // spread, same `agentId` / `topicId` fallbacks to the active conversation —
    // so the snapshot read and the store write can never land in different
    // buckets. `scope`, `groupId`, `threadId`, `documentId` and `subAgentId`
    // carry through the spread; `skipWorks` is a server-side Work-assembly
    // flag and takes no part in the key.
    const key = messageMapKey({
      ...query,
      agentId: query.agentId ?? state.activeAgentId,
      topicId: query.topicId !== undefined ? query.topicId : state.activeTopicId,
    });

    return dbMessageSelectors.getDbMessagesByKey(key)(state);
  };
};
