import { MessageSquarePlus, Trash2 } from "lucide-react";
import * as Switch from "@radix-ui/react-switch";
import type { Conversation } from "../../domain/conversation";
import type { ThemeMode } from "../../store/app-store";
import type { Verbosity } from "../../projectors";
import { ThemeToggle } from "../shared/ThemeToggle";
import { LlmBadge } from "../shared/LlmBadge";
import { cn } from "../../lib/cn";
import { focusRing, mutedText } from "../../lib/ui";

export function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  theme,
  onThemeChange,
  llmAvailable,
  developerMode,
  onDeveloperModeChange,
  verbosity,
  onVerbosityChange,
}: {
  readonly conversations: readonly Conversation[];
  readonly activeId: string | null;
  readonly onSelect: (id: string) => void;
  readonly onNew: () => void;
  readonly onDelete: (id: string) => void;
  readonly theme: ThemeMode;
  readonly onThemeChange: (theme: ThemeMode) => void;
  readonly llmAvailable: boolean | null;
  readonly developerMode: boolean;
  readonly onDeveloperModeChange: (enabled: boolean) => void;
  readonly verbosity: Verbosity;
  readonly onVerbosityChange: (verbosity: Verbosity) => void;
}) {
  return (
    <div className="flex h-full flex-col gap-2">
      <button
        type="button"
        className={cn(
          "flex w-full cursor-pointer items-center justify-center gap-2 rounded-[var(--radius-lg)]",
          "border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-sm font-medium",
          "text-[var(--text)] shadow-[var(--shadow-card)] hover:bg-[var(--fill-hover)]",
          focusRing,
        )}
        onClick={onNew}
      >
        <MessageSquarePlus size={16} />
        新对话
      </button>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <p className={cn("px-2 py-6 text-center text-xs", mutedText)}>暂无会话</p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
            {conversations.map((conversation) => {
              const active = conversation.id === activeId;
              return (
                <li key={conversation.id} className="group relative">
                  <button
                    type="button"
                    className={cn(
                      "w-full cursor-pointer rounded-[var(--radius-md)] border border-transparent",
                      "px-3 py-2.5 pr-9 text-left transition-colors",
                      active
                        ? "bg-[var(--fill-hover)] text-[var(--text)]"
                        : "text-[var(--text)] hover:bg-[var(--fill-hover)]",
                      focusRing,
                    )}
                    onClick={() => onSelect(conversation.id)}
                  >
                    <span className="block truncate text-sm font-medium">
                      {conversation.title}
                    </span>
                    <span className={cn("mt-0.5 block text-[11px]", mutedText)}>
                      {conversation.turns.length} 轮
                    </span>
                  </button>
                  <button
                    type="button"
                    className={cn(
                      "absolute top-1/2 right-1.5 -translate-y-1/2",
                      "inline-flex size-7 cursor-pointer items-center justify-center rounded-[var(--radius-sm)]",
                      "text-[var(--text-faint)] opacity-0 transition-opacity",
                      "hover:bg-[var(--fill-secondary)] hover:text-[var(--color-danger)]",
                      "group-hover:opacity-100 focus-visible:opacity-100",
                      focusRing,
                    )}
                    aria-label="删除对话"
                    onClick={(ev) => {
                      ev.stopPropagation();
                      onDelete(conversation.id);
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Footer settings — LobeHub bottom of nav */}
      <div className="mt-auto grid gap-2 border-t border-[var(--border-subtle)] pt-3">
        <div className="flex items-center justify-between gap-2 px-1">
          <LlmBadge available={llmAvailable} />
          <ThemeToggle theme={theme} onChange={onThemeChange} />
        </div>
        <label className="flex items-center justify-between gap-2 px-1 text-xs">
          <span className={mutedText}>开发者轨迹</span>
          <Switch.Root
            className={cn(
              "relative h-5 w-9 rounded-full bg-[var(--fill-secondary)]",
              "data-[state=checked]:bg-[var(--accent)]",
              focusRing,
            )}
            checked={developerMode}
            onCheckedChange={onDeveloperModeChange}
          >
            <Switch.Thumb
              className={cn(
                "block size-4 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform duration-200",
                "data-[state=checked]:translate-x-[18px]",
                "data-[state=checked]:bg-[var(--accent-fg)]",
              )}
            />
          </Switch.Root>
        </label>
        <label className="flex items-center justify-between gap-2 px-1 text-xs">
          <span className={mutedText}>详细度</span>
          <select
            className={cn(
              "rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--surface)]",
              "px-2 py-1 text-xs text-[var(--text)]",
              focusRing,
            )}
            value={verbosity}
            onChange={(e) => onVerbosityChange(e.target.value as Verbosity)}
          >
            <option value="minimal">简洁</option>
            <option value="standard">标准</option>
            <option value="verbose">完整</option>
          </select>
        </label>
      </div>
    </div>
  );
}
