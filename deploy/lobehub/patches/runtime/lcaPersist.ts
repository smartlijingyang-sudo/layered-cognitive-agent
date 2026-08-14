/** Write one assistant aggregate. No classification. */

import type {
  ChatImageItem,
  ChatMessageError,
  ChatToolPayload,
  ModelReasoning,
} from '@lobechat/types';

import { messageService } from '@/services/message';
import type { ChatStore } from '@/store/chat/store';

import type { FileRow } from './lcaArtifacts';

export type AssistantRowWrite = {
  content: string;
  error?: ChatMessageError;
  fileList?: FileRow[];
  imageList?: ChatImageItem[];
  model: string;
  operationId: string;
  reasoning?: ModelReasoning;
  tools?: ChatToolPayload[];
};

export async function persistAssistantRow(
  get: () => ChatStore,
  id: string,
  row: AssistantRowWrite,
): Promise<void> {
  const value: Record<string, unknown> = { content: row.content };
  if (row.error) value.error = row.error;
  if (row.reasoning) value.reasoning = row.reasoning;
  if (row.tools?.length) value.tools = row.tools;

  get().internal_dispatchMessage(
    { id, type: 'updateMessage', value },
    { operationId: row.operationId },
  );

  const ctx = get().internal_getConversationContext({ operationId: row.operationId });
  const result = await messageService.updateMessage(
    id,
    {
      content: row.content,
      imageList: row.imageList,
      model: row.model,
      provider: 'openai',
      ...(row.reasoning ? { reasoning: row.reasoning } : {}),
      ...(row.tools?.length ? { tools: row.tools } : {}),
      ...(row.error ? { error: row.error } : {}),
    },
    ctx,
  );

  if (result?.success && result.messages) {
    get().replaceMessages(result.messages, {
      action: 'optimisticUpdateMessageContent',
      context: ctx,
    });
  } else {
    await get().refreshMessages();
  }

  if (row.error) {
    get().internal_dispatchMessage(
      { id, type: 'updateMessage', value: { error: row.error } },
      { operationId: row.operationId },
    );
  }

  if (!row.tools?.length && (row.imageList?.length || row.fileList?.length)) {
    get().internal_dispatchMessage(
      {
        id,
        type: 'updateMessage',
        value: {
          ...(row.fileList?.length ? { fileList: row.fileList } : {}),
          ...(row.imageList?.length ? { imageList: row.imageList } : {}),
        },
      },
      { operationId: row.operationId },
    );
  }
}
