// Unit test for the LCA reaction store.
//
// No imports besides the store itself: vitest runs with `globals: true` in
// lobehub-ui, and `bun test` provides the same globals standalone, so this
// file works in both environments.

import { addReaction, getReactions, getSnapshot, reset, subscribe } from './reactionStore';

describe('reactionStore', () => {
  afterEach(() => {
    reset();
  });

  it('aggregates the same emoji into a count', () => {
    addReaction({ message_id: 'm1', emoji: '🎉', actor: 'alice' });
    addReaction({ message_id: 'm1', emoji: '🎉', actor: 'bob' });

    expect(getReactions('m1')).toEqual([{ emoji: '🎉', count: 2 }]);
  });

  it('keeps first-seen order across distinct emojis', () => {
    addReaction({ message_id: 'm1', emoji: '🎉', actor: 'alice' });
    addReaction({ message_id: 'm1', emoji: '❤️', actor: 'bob' });
    addReaction({ message_id: 'm1', emoji: '👍', actor: 'carol' });

    expect(getReactions('m1').map((reaction) => reaction.emoji)).toEqual(['🎉', '❤️', '👍']);
  });

  it('does not double-count an identical (message, emoji, actor) repeat', () => {
    addReaction({ message_id: 'm1', emoji: '🎉', actor: 'alice' });
    addReaction({ message_id: 'm1', emoji: '🎉', actor: 'alice' });

    expect(getReactions('m1')).toEqual([{ emoji: '🎉', count: 1 }]);
  });

  it('separates reactions by message id', () => {
    addReaction({ message_id: 'm1', emoji: '🎉', actor: 'alice' });
    addReaction({ message_id: 'm2', emoji: '🎉', actor: 'alice' });

    expect(getReactions('m1')).toEqual([{ emoji: '🎉', count: 1 }]);
    expect(getReactions('m2')).toEqual([{ emoji: '🎉', count: 1 }]);
  });

  it('ignores events without message_id or emoji', () => {
    addReaction({ message_id: '', emoji: '🎉', actor: 'alice' });
    addReaction({ message_id: 'm1', emoji: '', actor: 'alice' });

    expect(getReactions('m1')).toEqual([]);
  });

  it('notifies subscribers and bumps the snapshot version', () => {
    let notified = 0;
    const unsubscribe = subscribe(() => {
      notified += 1;
    });

    const before = getSnapshot();
    addReaction({ message_id: 'm1', emoji: '🎉', actor: 'alice' });

    expect(notified).toBe(1);
    expect(getSnapshot()).toBe(before + 1);

    unsubscribe();
    addReaction({ message_id: 'm1', emoji: '👍', actor: 'alice' });
    expect(notified).toBe(1);
  });
});