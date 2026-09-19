// ADR-0244 D1: unit tests for assistant placeholder filtering.
//
// Copied into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/executeGatewayRun.test.ts`
// by `lca_runtime_agent_gateway`; run from the lobehub-ui root:
//   bunx vitest run src/store/chat/agents/transports/lcaGateway/executeGatewayRun.test.ts

import { describe, expect, it } from 'vitest';

import { isPlaceholderAssistantRow } from './executeGatewayRun';

describe('isPlaceholderAssistantRow', () => {
  it('returns true for optimistic placeholder and empty rows', () => {
    expect(isPlaceholderAssistantRow({ role: 'assistant', content: '...' })).toBe(true);
    expect(isPlaceholderAssistantRow({ role: 'assistant', content: '' })).toBe(true);
    expect(isPlaceholderAssistantRow({ role: 'assistant', content: 'LOADING_FLAT' })).toBe(true);
  });

  it('returns false for real assistant replies', () => {
    expect(isPlaceholderAssistantRow({ role: 'assistant', content: 'real reply' })).toBe(false);
  });

  it('returns false for assistant rows with tools, reasoning, or attachments', () => {
    expect(isPlaceholderAssistantRow({ role: 'assistant', content: '...', tools: [{ id: 't1' }] })).toBe(false);
    expect(isPlaceholderAssistantRow({ role: 'assistant', content: '...', reasoning: { content: 'thinking' } })).toBe(false);
    expect(isPlaceholderAssistantRow({ role: 'assistant', content: '...', fileList: [{ id: 'f1' }] })).toBe(false);
  });

  it('returns false for user rows', () => {
    expect(isPlaceholderAssistantRow({ role: 'user', content: '...' })).toBe(false);
  });
});
