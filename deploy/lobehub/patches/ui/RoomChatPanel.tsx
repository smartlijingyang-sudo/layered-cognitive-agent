'use client';

import { Flexbox, Tag } from '@lobehub/ui';
import { createStaticStyles } from 'antd-style';
import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
} from 'react';

// ── Types (mirror lca.contracts.models.collaboration.peer) ────────────────

interface RoomSpec {
  room_id: string;
  display_name: string;
  coordinator_agent_id: string;
  member_peer_ids: string[];
  shared_topic_id: string;
  routing_policy: 'coordinator_first' | 'mention_only';
}

type RoomMessageKind = 'user' | 'run_started' | 'peer' | 'folded' | 'approval';

interface RoomMessage {
  message_id: string;
  room_id: string;
  kind: RoomMessageKind;
  sender_id: string;
  content: string;
  correlation_id: string;
  run_id: string;
  payload: Record<string, unknown>;
  created_at_ms: number;
}

interface MentionOption {
  id: string;
  name: string;
}

const API_BASE = '/lca-api/v1/rooms';

// ── Helpers ───────────────────────────────────────────────────────────────

function peerDisplayName(peerId: string): string {
  return peerId.split('/').pop()?.replace(/^arch_/, '') || peerId;
}

function buildMembers(room: RoomSpec): MentionOption[] {
  const seen = new Set<string>();
  const members: MentionOption[] = [];
  for (const id of [room.coordinator_agent_id, ...room.member_peer_ids]) {
    if (!id || seen.has(id)) continue;
    seen.add(id);
    members.push({ id, name: peerDisplayName(id) });
  }
  return members;
}

function formatTime(ms: number): string {
  if (!ms) return '';
  return new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function findMentionToken(value: string, caret: number): string | null {
  const before = value.slice(0, caret);
  const atIndex = before.lastIndexOf('@');
  if (atIndex < 0) return null;
  if (atIndex > 0 && !/\s/.test(value[atIndex - 1])) return null;
  const token = before.slice(atIndex + 1);
  if (/\s/.test(token)) return null;
  return token;
}

// ── API calls ─────────────────────────────────────────────────────────────

async function fetchRooms(): Promise<RoomSpec[]> {
  const resp = await fetch(API_BASE);
  if (!resp.ok) throw new Error(`GET /v1/rooms failed: ${resp.status}`);
  const body = (await resp.json()) as { rooms?: RoomSpec[] };
  return Array.isArray(body.rooms) ? body.rooms : [];
}

async function fetchMessages(roomId: string): Promise<RoomMessage[]> {
  const resp = await fetch(`${API_BASE}/${encodeURIComponent(roomId)}/messages`);
  if (!resp.ok) throw new Error(`GET messages failed: ${resp.status}`);
  const body = (await resp.json()) as { messages?: RoomMessage[] };
  return Array.isArray(body.messages) ? body.messages : [];
}

async function postMessage(roomId: string, content: string, senderId: string): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/${encodeURIComponent(roomId)}/messages`, {
    body: JSON.stringify({ content, sender_id: senderId }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
  return resp.status === 202 || resp.ok;
}

// ── Styles ────────────────────────────────────────────────────────────────

const styles = createStaticStyles(({ css, cssVar }) => {
  const rowBase = css`
    align-items: flex-start;
    padding: 2px 0;
  `;
  return {
    fab: css`
      background: ${cssVar.colorBgElevated};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 999px;
      bottom: 20px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
      color: ${cssVar.colorText};
      cursor: pointer;
      font-size: 13px;
      left: 20px;
      padding: 8px 14px;
      position: fixed;
      z-index: 1200;
    `,
    panel: css`
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: ${cssVar.borderRadiusLG};
      bottom: 64px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
      display: flex;
      flex-direction: column;
      height: 540px;
      left: 20px;
      overflow: hidden;
      position: fixed;
      width: 680px;
      z-index: 1200;
    `,
    header: css`
      align-items: center;
      border-bottom: 1px solid ${cssVar.colorBorderSecondary};
      display: flex;
      gap: 8px;
      justify-content: space-between;
      padding: 10px 12px;
    `,
    headerTitle: css`
      color: ${cssVar.colorText};
      font-size: 14px;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    `,
    headerMeta: css`
      color: ${cssVar.colorTextTertiary};
      font-size: 12px;
    `,
    headerActions: css`
      align-items: center;
      display: flex;
      gap: 4px;
    `,
    iconButton: css`
      background: transparent;
      border: none;
      border-radius: 6px;
      color: ${cssVar.colorTextSecondary};
      cursor: pointer;
      font-size: 14px;
      line-height: 1;
      padding: 4px 8px;

      &:hover {
        background: ${cssVar.colorFillTertiary};
      }
    `,
    backButton: css`
      background: transparent;
      border: none;
      border-radius: 6px;
      color: ${cssVar.colorTextSecondary};
      cursor: pointer;
      font-size: 16px;
      line-height: 1;
      padding: 4px 8px;

      &:hover {
        background: ${cssVar.colorFillTertiary};
      }
    `,
    chipsRow: css`
      align-items: center;
      border-bottom: 1px solid ${cssVar.colorBorderSecondary};
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 8px 12px;
    `,
    chipsLabel: css`
      color: ${cssVar.colorTextTertiary};
      font-size: 12px;
      margin-right: 2px;
    `,
    messages: css`
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 12px;
    `,
    empty: css`
      color: ${cssVar.colorTextTertiary};
      font-size: 13px;
      padding: 32px 0;
      text-align: center;
    `,
    error: css`
      background: ${cssVar.colorErrorBg};
      color: ${cssVar.colorErrorText};
      font-size: 12px;
      padding: 6px 12px;
    `,
    systemLine: css`
      color: ${cssVar.colorTextTertiary};
      font-size: 12px;
      padding: 4px 0;
      text-align: center;
    `,
    userRow: css`
      ${rowBase}
      justify-content: flex-end;
    `,
    userBubble: css`
      background: ${cssVar.colorPrimary};
      border-radius: 10px 10px 2px 10px;
      color: ${cssVar.colorTextLightSolid};
      font-size: 13px;
      max-width: 72%;
      padding: 8px 10px;
    `,
    peerRow: css`
      ${rowBase}
      justify-content: flex-start;
    `,
    peerBubble: css`
      background: ${cssVar.colorFillQuaternary};
      border-radius: 10px 10px 10px 2px;
      color: ${cssVar.colorText};
      font-size: 13px;
      max-width: 72%;
      padding: 8px 10px;
    `,
    peerName: css`
      color: ${cssVar.colorTextTertiary};
      font-size: 11px;
      margin-bottom: 2px;
    `,
    bubbleTime: css`
      color: ${cssVar.colorTextLightSolid};
      font-size: 10px;
      margin-top: 4px;
      opacity: 0.8;
    `,
    foldedCard: css`
      background: ${cssVar.colorFillQuaternary};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: ${cssVar.borderRadius};
      font-size: 13px;
      margin: 6px 0;
      padding: 8px 10px;
    `,
    foldedHeader: css`
      color: ${cssVar.colorTextSecondary};
      font-size: 12px;
      font-weight: 600;
      margin-bottom: 4px;
    `,
    foldedBody: css`
      color: ${cssVar.colorText};
      white-space: pre-wrap;
      word-break: break-word;
    `,
    composer: css`
      align-items: flex-end;
      border-top: 1px solid ${cssVar.colorBorderSecondary};
      display: flex;
      gap: 8px;
      padding: 10px 12px;
    `,
    inputWrapper: css`
      flex: 1;
      position: relative;
    `,
    input: css`
      background: ${cssVar.colorFillQuaternary};
      border: 1px solid ${cssVar.colorBorder};
      border-radius: ${cssVar.borderRadius};
      box-sizing: border-box;
      color: ${cssVar.colorText};
      font-size: 13px;
      line-height: 1.5;
      min-height: 40px;
      padding: 8px 10px;
      resize: vertical;
      width: 100%;

      &:focus {
        border-color: ${cssVar.colorPrimary};
        outline: none;
      }
    `,
    mentionMenu: css`
      background: ${cssVar.colorBgElevated};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: ${cssVar.borderRadius};
      bottom: calc(100% + 4px);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
      left: 0;
      max-height: 180px;
      overflow-y: auto;
      position: absolute;
      width: 260px;
      z-index: 10;
    `,
    mentionItem: css`
      align-items: center;
      background: transparent;
      border: none;
      color: ${cssVar.colorText};
      cursor: pointer;
      display: flex;
      font-size: 13px;
      gap: 8px;
      justify-content: space-between;
      padding: 8px 10px;
      text-align: left;
      width: 100%;

      &:hover {
        background: ${cssVar.colorFillTertiary};
      }
    `,
    mentionItemActive: css`
      align-items: center;
      background: ${cssVar.colorFillTertiary};
      border: none;
      color: ${cssVar.colorText};
      cursor: pointer;
      display: flex;
      font-size: 13px;
      gap: 8px;
      justify-content: space-between;
      padding: 8px 10px;
      text-align: left;
      width: 100%;
    `,
    mentionName: css`
      font-weight: 500;
    `,
    mentionId: css`
      color: ${cssVar.colorTextTertiary};
      font-size: 11px;
    `,
    sendButton: css`
      background: ${cssVar.colorPrimary};
      border: none;
      border-radius: ${cssVar.borderRadius};
      color: ${cssVar.colorTextLightSolid};
      cursor: pointer;
      font-size: 13px;
      padding: 8px 16px;

      &:disabled {
        cursor: not-allowed;
        opacity: 0.5;
      }
    `,
    roomList: css`
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 8px;
    `,
    roomCard: css`
      background: transparent;
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: ${cssVar.borderRadius};
      color: ${cssVar.colorText};
      cursor: pointer;
      display: block;
      font-size: 13px;
      margin-bottom: 8px;
      padding: 10px 12px;
      text-align: left;
      width: 100%;

      &:hover {
        background: ${cssVar.colorFillTertiary};
        border-color: ${cssVar.colorPrimaryHover};
      }
    `,
    roomName: css`
      font-size: 14px;
      font-weight: 600;
    `,
    roomMeta: css`
      align-items: center;
      display: flex;
      gap: 12px;
      justify-content: space-between;
      margin-top: 4px;
    `,
    roomMetaText: css`
      color: ${cssVar.colorTextSecondary};
      font-size: 12px;
    `,
    roomPolicy: css`
      color: ${cssVar.colorTextTertiary};
      font-size: 11px;
    `,
  };
});

// ── Component ─────────────────────────────────────────────────────────────

const RoomChatPanelInner = () => {
  const [open, setOpen] = useState(false);
  const [rooms, setRooms] = useState<RoomSpec[]>([]);
  const [activeRoomId, setActiveRoomId] = useState<string | null>(null);
  const [messages, setMessages] = useState<RoomMessage[]>([]);
  const [input, setInput] = useState('');
  const [loadingRooms, setLoadingRooms] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState('');
  const [mentionIndex, setMentionIndex] = useState(0);

  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const messageEndRef = useRef<HTMLDivElement | null>(null);

  const activeRoom = useMemo(
    () => rooms.find((room) => room.room_id === activeRoomId) ?? null,
    [rooms, activeRoomId],
  );

  const refreshRooms = useCallback(async () => {
    setLoadingRooms(true);
    try {
      setRooms(await fetchRooms());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载房间失败');
    } finally {
      setLoadingRooms(false);
    }
  }, []);

  const refreshMessages = useCallback(async (roomId: string) => {
    setLoadingMessages(true);
    try {
      setMessages(await fetchMessages(roomId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载消息失败');
    } finally {
      setLoadingMessages(false);
    }
  }, []);

  useEffect(() => {
    if (open) void refreshRooms();
  }, [open, refreshRooms]);

  useEffect(() => {
    if (!open || !activeRoomId) return;
    void refreshMessages(activeRoomId);
    const timer = window.setInterval(() => {
      void refreshMessages(activeRoomId);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [open, activeRoomId, refreshMessages]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, activeRoomId]);

  const openRoom = (roomId: string) => {
    setActiveRoomId(roomId);
    setMessages([]);
    setError(null);
  };

  const backToList = () => {
    setActiveRoomId(null);
    setMessages([]);
    setInput('');
    setMentionOpen(false);
    setError(null);
  };

  const members = useMemo(() => (activeRoom ? buildMembers(activeRoom) : []), [activeRoom]);

  const mentionOptions = useMemo(() => {
    if (!mentionOpen) return [];
    return members.filter(
      (member) => member.id.includes(mentionQuery) || member.name.includes(mentionQuery),
    );
  }, [mentionOpen, mentionQuery, members]);

  const selectMention = useCallback(
    (option: MentionOption) => {
      const el = inputRef.current;
      const caret = el?.selectionStart ?? input.length;
      const before = input.slice(0, caret);
      const atIndex = before.lastIndexOf('@');
      if (atIndex < 0) {
        setMentionOpen(false);
        return;
      }
      const prefix = before.slice(0, atIndex);
      const suffix = input.slice(caret);
      const next = `${prefix}@${option.id} ${suffix}`;
      setInput(next);
      setMentionOpen(false);
      requestAnimationFrame(() => {
        const target = inputRef.current;
        if (target) {
          target.focus();
          const pos = prefix.length + option.id.length + 2;
          target.setSelectionRange(pos, pos);
        }
      });
    },
    [input],
  );

  const handleInputChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    const value = event.target.value;
    const caret = event.target.selectionStart ?? value.length;
    setInput(value);
    const token = findMentionToken(value, caret);
    if (token !== null) {
      setMentionQuery(token);
      setMentionIndex(0);
      setMentionOpen(true);
    } else {
      setMentionOpen(false);
    }
  };

  const handleSend = useCallback(async () => {
    const content = input.trim();
    if (!content || !activeRoomId || sending) return;
    setSending(true);
    try {
      await postMessage(activeRoomId, content, 'user');
      setInput('');
      setMentionOpen(false);
      await refreshMessages(activeRoomId);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送失败');
    } finally {
      setSending(false);
    }
  }, [input, activeRoomId, sending, refreshMessages]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionOpen && mentionOptions.length > 0) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setMentionIndex((index) => (index + 1) % mentionOptions.length);
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setMentionIndex(
          (index) => (index - 1 + mentionOptions.length) % mentionOptions.length,
        );
        return;
      }
      if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault();
        selectMention(mentionOptions[mentionIndex]);
        return;
      }
      if (event.key === 'Escape') {
        setMentionOpen(false);
        return;
      }
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const renderMessage = (msg: RoomMessage) => {
    const time = formatTime(msg.created_at_ms);
    switch (msg.kind) {
      case 'user':
        return (
          <Flexbox key={msg.message_id} horizontal className={styles.userRow}>
            <div className={styles.userBubble}>
              <div>{msg.content}</div>
              <div className={styles.bubbleTime}>{time}</div>
            </div>
          </Flexbox>
        );
      case 'run_started':
        return (
          <div key={msg.message_id} className={styles.systemLine}>
            🚀 run{msg.run_id ? ` #${msg.run_id}` : ''} 已启动 · {time}
          </div>
        );
      case 'folded':
        return (
          <div key={msg.message_id} className={styles.foldedCard}>
            <div className={styles.foldedHeader}>🧩 结论汇总 · {time}</div>
            <div className={styles.foldedBody}>{msg.content}</div>
          </div>
        );
      case 'peer':
        return (
          <Flexbox key={msg.message_id} horizontal className={styles.peerRow}>
            <div className={styles.peerBubble}>
              <div className={styles.peerName}>{peerDisplayName(msg.sender_id)}</div>
              <div>{msg.content}</div>
            </div>
          </Flexbox>
        );
      default:
        return (
          <div key={msg.message_id} className={styles.systemLine}>
            {msg.content || msg.kind} · {time}
          </div>
        );
    }
  };

  return (
    <>
      <button
        aria-label="打开群聊房间"
        className={styles.fab}
        type="button"
        onClick={() => setOpen((value) => !value)}
      >
        💬 群聊
      </button>
      {open ? (
        <div className={styles.panel}>
          <div className={styles.header}>
            <Flexbox horizontal align="center" gap={8} flex={1} style={{ minWidth: 0 }}>
              {activeRoom ? (
                <>
                  <button
                    aria-label="返回房间列表"
                    className={styles.backButton}
                    type="button"
                    onClick={backToList}
                  >
                    ←
                  </button>
                  <span className={styles.headerTitle}>{activeRoom.display_name}</span>
                  <span className={styles.headerMeta}>{activeRoom.routing_policy}</span>
                </>
              ) : (
                <span className={styles.headerTitle}>群聊房间</span>
              )}
            </Flexbox>
            <Flexbox horizontal align="center" className={styles.headerActions}>
              <button
                aria-label="刷新"
                className={styles.iconButton}
                type="button"
                onClick={() => {
                  if (activeRoom) void refreshMessages(activeRoom.room_id);
                  else void refreshRooms();
                }}
              >
                ⟳
              </button>
              <button
                aria-label="关闭"
                className={styles.iconButton}
                type="button"
                onClick={() => setOpen(false)}
              >
                ✕
              </button>
            </Flexbox>
          </div>

          {activeRoom ? (
            <>
              <Flexbox horizontal align="center" wrap="wrap" className={styles.chipsRow}>
                <span className={styles.chipsLabel}>成员:</span>
                {members.map((member) => (
                  <Tag key={member.id} color="blue">
                    {member.name}
                  </Tag>
                ))}
              </Flexbox>
              <div className={styles.messages}>
                {messages.length === 0 && !loadingMessages ? (
                  <div className={styles.empty}>还没有消息，发一条开始协作吧</div>
                ) : (
                  messages.map(renderMessage)
                )}
                <div ref={messageEndRef} />
              </div>
              {error ? <div className={styles.error}>{error}</div> : null}
              <div className={styles.composer}>
                <div className={styles.inputWrapper}>
                  <textarea
                    ref={inputRef}
                    className={styles.input}
                    placeholder="输入消息，@成员 可点名协作…"
                    rows={2}
                    value={input}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                  />
                  {mentionOpen && mentionOptions.length > 0 ? (
                    <div className={styles.mentionMenu}>
                      {mentionOptions.map((option, idx) => (
                        <button
                          key={option.id}
                          type="button"
                          className={idx === mentionIndex ? styles.mentionItemActive : styles.mentionItem}
                          onMouseDown={(event) => event.preventDefault()}
                          onMouseEnter={() => setMentionIndex(idx)}
                          onClick={() => selectMention(option)}
                        >
                          <span className={styles.mentionName}>{option.name}</span>
                          <span className={styles.mentionId}>{option.id}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <button
                  className={styles.sendButton}
                  disabled={sending || !input.trim()}
                  type="button"
                  onClick={() => void handleSend()}
                >
                  {sending ? '发送中' : '发送'}
                </button>
              </div>
            </>
          ) : (
            <div className={styles.roomList}>
              {loadingRooms && rooms.length === 0 ? (
                <div className={styles.empty}>加载中…</div>
              ) : rooms.length === 0 ? (
                <div className={styles.empty}>暂无房间</div>
              ) : (
                rooms.map((room) => {
                  const memberCount = buildMembers(room).length;
                  return (
                    <button
                      key={room.room_id}
                      className={styles.roomCard}
                      type="button"
                      onClick={() => openRoom(room.room_id)}
                    >
                      <div className={styles.roomName}>{room.display_name}</div>
                      <div className={styles.roomMeta}>
                        <span className={styles.roomMetaText}>{memberCount} 位成员</span>
                        <span className={styles.roomPolicy}>{room.routing_policy}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          )}
        </div>
      ) : null}
    </>
  );
};

const RoomChatPanel = memo(() => <RoomChatPanelInner />);

RoomChatPanel.displayName = 'RoomChatPanel';

export default RoomChatPanel;