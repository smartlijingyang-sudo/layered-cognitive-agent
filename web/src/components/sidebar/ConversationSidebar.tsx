import { MessageSquarePlus, Trash2 } from "lucide-react";
import type { Conversation } from "../../domain/conversation";
import { cn } from "../../lib/cn";
import { focusRing, iconButton, mutedText } from "../../lib/ui";

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
    <aside>
      <div className="flex items-center justify-between gap-2">
        <h2 className="m-0 text-base font-semibold">会话</h2>
        <button type="button" className={iconButton} onClick={onNew} aria-label="新建对话">
          <MessageSquarePlus size={16} />
        </button>
      </div>
      <ul className="mt-4 flex list-none flex-col gap-1.5 p-0">
        {conversations.map((conversation) => {
          const active = conversation.id === activeId;
          return (
            <li key={conversation.id} className="grid grid-cols-[1fr_auto] gap-1">
              <button
                type="button"
                className={cn(
                  "cursor-pointer rounded-[var(--radius-md)] border px-3 py-2.5 text-left text-inherit transition-colors",
                  active
                    ? "border-accent bg-[color-mix(in_srgb,var(--accent)_12%,transparent)]"
                    : "border-transparent bg-transparent hover:border-border hover:bg-surface-elevated",
                  focusRing,
                )}
                onClick={() => onSelect(conversation.id)}
              >
                <span className="block font-semibold">{conversation.title}</span>
                <span className={cn("block text-sm", mutedText)}>
                  {conversation.turns.length} 轮
                </span>
              </button>
              <button
                type="button"
                className={cn(iconButton, "text-danger hover:border-danger/40")}
                aria-label="删除对话"
                onClick={() => onDelete(conversation.id)}
              >
                <Trash2 size={14} />
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
