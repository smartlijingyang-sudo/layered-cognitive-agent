// ADR-0244 D1: unit tests for token-budget-aware wire message slicing.
//
// Copied into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/executeGatewayRun.test.ts`
// by `lca_runtime_agent_gateway`; run from the lobehub-ui root:
//   bunx vitest run src/store/chat/agents/transports/lcaGateway/executeGatewayRun.test.ts

import { describe, expect, it } from 'vitest';

import { sliceWireMessages } from './executeGatewayRun';

const user = (id: string, content = `user message ${id}`) => ({
  id,
  role: 'user',
  content,
});

const assistant = (id: string, content = `assistant reply ${id}`) => ({
  id,
  role: 'assistant',
  content,
});

describe('sliceWireMessages', () => {
  it('drops assistant placeholder rows', () => {
    const messages = [
      { id: 'p1', role: 'assistant', content: '...' },
      user('u1'),
      { id: 'p2', role: 'assistant', content: '' },
    ];
    const wire = sliceWireMessages(messages, 100_000);
    expect(wire).toEqual([{ role: 'user', content: 'user message u1' }]);
  });

  it('keeps attachments on their originating turn', () => {
    const messages = [
      user('u1'),
      {
        id: 'u2',
        role: 'user',
        content: 'here is the file',
        fileList: [{ id: 'f1', name: 'report.pdf', url: '/files/f1', fileType: 'pdf' }],
      },
    ];
    const wire = sliceWireMessages(messages, 100_000);
    expect(wire).toHaveLength(2);
    expect(wire[1]).toMatchObject({
      role: 'user',
      content: 'here is the file',
      fileList: [{ id: 'f1', name: 'report.pdf', url: '/files/f1', fileType: 'pdf' }],
    });
  });

  it('truncates history when the budget is exceeded and keeps the current turn', () => {
    const longContent = 'This is a fairly long message '.repeat(20);
    const messages = [
      user('u1', longContent + 'first'),
      assistant('a1', longContent + 'first reply'),
      user('u2', longContent + 'second'),
      assistant('a2', longContent + 'second reply'),
      user('u3', longContent + 'current turn'),
    ];
    const wire = sliceWireMessages(messages, 100);
    expect(wire.length).toBeGreaterThan(0);
    expect(wire[wire.length - 1]).toEqual({ role: 'user', content: longContent + 'current turn' });
    expect(wire.length).toBeLessThan(messages.length);
  });

  it('returns all messages when no context window is known', () => {
    const messages = [user('u1'), assistant('a1'), user('u2')];
    const wire = sliceWireMessages(messages, undefined);
    expect(wire).toHaveLength(3);
  });

  it('falls back to an empty user message when nothing remains', () => {
    const wire = sliceWireMessages([{ id: 'p', role: 'assistant', content: '...' }], 100_000);
    expect(wire).toEqual([{ role: 'user', content: '' }]);
  });
});