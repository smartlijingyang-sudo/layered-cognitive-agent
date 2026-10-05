import useSWR from 'swr';

import { useChatStore } from '@/store/chat';
import { topicSelectors } from '@/store/chat/selectors';

/** Matches the LCA cron daemon tick, so a fire is picked up within one cycle. */
const POLL_INTERVAL_MS = 30_000;

interface LcaRunningOperationRow {
  agent_id?: string;
  assistant_message_id?: string | null;
  run_id: string;
  scope?: string;
  topic_id?: string;
}

function bearer(): string {
  const envToken =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env?.NEXT_PUBLIC_LCA_TOKEN
      : undefined;
  return envToken && envToken.length > 0 ? envToken : 'lca-local';
}

async function fetchLiveOperation(topicId: string): Promise<LcaRunningOperationRow | null> {
  const resp = await fetch(`/lca-api/v1/topics/${encodeURIComponent(topicId)}/running-op`, {
    headers: { Authorization: `Bearer ${bearer()}` },
  });
  if (!resp.ok) return null;
  const body = (await resp.json()) as { running_operation: LcaRunningOperationRow | null };
  return body.running_operation ?? null;
}

/**
 * Pull a run this browser did not start into the topic map.
 *
 * A cron handoff fires on the server and streams to `agent_runtime_stream:<run_id>`.
 * The browser files messages by the operationId it captured when it started a run,
 * and `agent_runtime_init` is the only event carrying `topicId`, with no branch for
 * it in the gateway handler. So a run the server started on its own is invisible
 * here unless something resolves the topic to it.
 *
 * The endpoint answers only for a live run, so a poll that finds one is a run worth
 * attaching to. Seeding `metadata.runningOperation` hands off to the existing
 * `useGatewayReconnect`, which is left untouched.
 *
 * Stops by itself: once the topic map holds an operationId the SWR key goes null.
 */
export const useCronHandoffWatch = (topicId: string | null | undefined) => {
  const knownOperationId = useChatStore((s): string | null | undefined => {
    if (!topicId) return undefined;
    const topic = topicSelectors.getTopicById(topicId)(s);
    if (!topic) return undefined;
    return topic.metadata?.runningOperation?.operationId ?? null;
  });

  useSWR(
    topicId && knownOperationId === null ? ['lca-cron-handoff-watch', topicId] : null,
    async () => {
      const row = await fetchLiveOperation(topicId!);
      if (!row?.run_id) return false;

      const store = useChatStore.getState();
      // The browser already owns this run when it started it itself. Attaching a
      // second time would double-file every event.
      const operations = (store as { operations?: Record<string, unknown> }).operations;
      if (operations?.[row.run_id]) return false;

      const topic = topicSelectors.getTopicById(topicId)(store);
      if (!topic) return false;
      if (topic.metadata?.runningOperation?.operationId === row.run_id) return false;

      store.internal_dispatchTopic(
        {
          id: topicId,
          type: 'updateTopic',
          value: {
            metadata: {
              ...(topic.metadata ?? {}),
              runningOperation: {
                assistantMessageId: row.assistant_message_id ?? undefined,
                operationId: row.run_id,
                scope: row.scope ?? 'main',
              },
            },
          },
        },
        'useCronHandoffWatch',
      );
      return true;
    },
    {
      refreshInterval: POLL_INTERVAL_MS,
      revalidateOnFocus: true,
      shouldRetryOnError: false,
    },
  );
};
