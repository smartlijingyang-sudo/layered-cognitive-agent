/** LCA failure → LobeHub ChatMessageError. No store I/O. */

import { AgentRuntimeErrorType, refineErrorCode } from '@lobechat/model-runtime';
import type { ChatMessageError } from '@lobechat/types';

export function toLcaChatMessageError(error: unknown): ChatMessageError {
  const message = errorMessage(error);
  return {
    body: { message, provider: 'openai' },
    message,
    type: refineLcaErrorType(message),
  };
}

function refineLcaErrorType(message: string): ChatMessageError['type'] {
  return (
    refineErrorCode({
      errorType: AgentRuntimeErrorType.AgentRuntimeError,
      message,
    }) ??
    (/\b429\b/.test(message)
      ? AgentRuntimeErrorType.RateLimitExceeded
      : AgentRuntimeErrorType.AgentRuntimeError)
  );
}

function errorMessage(error: unknown): string {
  if (typeof error === 'string') return error;
  if (error instanceof Error) return error.message;
  if (error && typeof error === 'object' && 'message' in error) {
    const value = (error as { message: unknown }).message;
    if (typeof value === 'string') return value;
  }
  return error == null ? '' : String(error);
}
