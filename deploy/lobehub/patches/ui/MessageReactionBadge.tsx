'use client';

import { createStaticStyles } from 'antd-style';
import { memo, useSyncExternalStore } from 'react';

import {
  getReactions,
  getSnapshot,
  subscribe,
} from '@/store/chat/agents/transports/lcaGateway/reactionStore';

const styles = createStaticStyles(({ css, cssVar }) => ({
  container: css`
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding-top: 4px;
  `,
  chip: css`
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 22px;
    padding-inline: 8px;
    border-radius: 11px;
    font-size: 12px;
    line-height: 1;
    background: ${cssVar.colorFillSecondary};
    border: 1px solid ${cssVar.colorBorderSecondary};
    color: ${cssVar.colorText};
  `,
  count: css`
    font-size: 11px;
    color: ${cssVar.colorTextSecondary};
  `,
}));

interface MessageReactionBadgeProps {
  messageId: string;
}

/**
 * Renders the LCA `reaction_added` badges for one message bubble. Reads the
 * shared reaction store (fed by the gateway event handler); never writes.
 */
const MessageReactionBadge = memo<MessageReactionBadgeProps>(({ messageId }) => {
  useSyncExternalStore(subscribe, getSnapshot);

  const reactions = getReactions(messageId);
  if (reactions.length === 0) return null;

  return (
    <div className={styles.container}>
      {reactions.map((reaction) => (
        <span className={styles.chip} key={reaction.emoji}>
          <span>{reaction.emoji}</span>
          {reaction.count > 1 && <span className={styles.count}>×{reaction.count}</span>}
        </span>
      ))}
    </div>
  );
});

MessageReactionBadge.displayName = 'MessageReactionBadge';

export default MessageReactionBadge;