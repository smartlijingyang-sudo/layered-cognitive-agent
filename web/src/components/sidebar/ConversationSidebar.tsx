import { MessageSquarePlus, Trash2 } from "lucide-react";
import type { Conversation } from "../../domain/conversation";

export function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: {
  readonly conversations: readonly Conversation[];
  readonly activeId: string | null;
  readonly onSelect: (id: string) => void;
  readonly onNew: () => void;
  readonly onDelete: (id: string) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>会话</h2>
        <button type="button" className="icon-button" onClick={onNew} aria-label="新建对话">
          <MessageSquarePlus size={16} />
        </button>
      </div>
      <ul className="conversation-list">
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            <button
              type="button"
              className={`conversation-item ${conversation.id === activeId ? "active" : ""}`}
              onClick={() => onSelect(conversation.id)}
            >
              <span className="conversation-title">{conversation.title}</span>
              <span className="conversation-meta">{conversation.turns.length} 轮</span>
            </button>
            <button
              type="button"
              className="icon-button danger"
              aria-label="删除对话"
              onClick={() => onDelete(conversation.id)}
            >
              <Trash2 size={14} />
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
