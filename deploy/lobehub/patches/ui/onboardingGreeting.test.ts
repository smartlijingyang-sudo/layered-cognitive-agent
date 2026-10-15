import { describe, expect, it } from 'vitest';

import { buildOnboardingGreetingMessages } from './onboardingGreeting';

describe('buildOnboardingGreetingMessages', () => {
  const context = { agentId: 'agt_test', topicId: 'tpc_test' };

  it('backdates greeting bubbles before the earliest existing message when the conversation already started', () => {
    const userMessageTime = new Date('2026-10-15T01:42:59Z').getTime();
    const existing = [{ createdAt: userMessageTime }];

    const bubbles = buildOnboardingGreetingMessages(
      context,
      existing,
      ['你好！我是你的专属个人 Agent。', '在正式开始之前，我该怎么称呼你呢？'],
    );

    expect(bubbles).toHaveLength(2);
    for (const bubble of bubbles) {
      expect(bubble.createdAt).toBeLessThan(userMessageTime);
    }
    // First scripted bubble must sort before the second one.
    expect(bubbles[0].createdAt).toBeLessThan(bubbles[1].createdAt);
    expect(bubbles[1].createdAt - bubbles[0].createdAt).toBe(1000);
  });

  it('uses the current time when the conversation is still empty', () => {
    const before = Date.now();
    const bubbles = buildOnboardingGreetingMessages(context, [], ['hello']);
    const after = Date.now();

    expect(bubbles).toHaveLength(1);
    expect(bubbles[0].createdAt).toBeGreaterThanOrEqual(before);
    expect(bubbles[0].createdAt).toBeLessThanOrEqual(after);
  });

  it('falls back to the current time when existing createdAt values are malformed', () => {
    const before = Date.now();
    const bubbles = buildOnboardingGreetingMessages(
      context,
      [{ createdAt: 'not-a-date' as unknown as Date }, { createdAt: undefined }],
      ['hello'],
    );
    const after = Date.now();

    expect(bubbles).toHaveLength(1);
    expect(bubbles[0].createdAt).toBeGreaterThanOrEqual(before);
    expect(bubbles[0].createdAt).toBeLessThanOrEqual(after);
  });

  it('keeps bubbles oldest-first with more than two scripted messages', () => {
    const userMessageTime = new Date('2026-10-15T01:00:00Z').getTime();
    const existing = [{ createdAt: userMessageTime }];

    const bubbles = buildOnboardingGreetingMessages(context, existing, ['a', 'b', 'c']);

    expect(bubbles).toHaveLength(3);
    for (const bubble of bubbles) {
      expect(bubble.createdAt).toBeLessThan(userMessageTime);
    }
    for (let i = 1; i < bubbles.length; i++) {
      expect(bubbles[i - 1].createdAt).toBeLessThan(bubbles[i].createdAt);
    }
  });
});