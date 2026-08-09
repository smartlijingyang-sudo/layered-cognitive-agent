import {
  Hash,
  MessageSquareDashed,
  MessageSquarePlus,
  Trash2,
} from "lucide-react";
import * as Switch from "@radix-ui/react-switch";
import type { Conversation } from "../../domain/conversation";
import type { ThemeMode } from "../../store/app-store";
import type { Verbosity } from "../../projectors";
import { ThemeToggle } from "../shared/ThemeToggle";
import { LlmBadge } from "../shared/LlmBadge";
import { cn } from "../../lib/cn";
import { LobeIcon } from "../../lib/icons";
import { focusRing, mutedText } from "../../lib/ui";

function formatRelativeTime(ts: number | undefined): string {
  if (!ts) return "";
  const diff = Date.now() - ts;
  const min = Math.floor(diff / 60_000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day} 天前`;
  return new Date(ts).toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

export function ConversationSidebar({
  conversations,
  activeId,
  homeActive,
  onSelect,
  onNew,
  onHome,
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
  /** True when home (no chat selected) is the right-panel view. */
  readonly homeActive?: boolean;
  readonly onSelect: (id: string) => void;
  readonly onNew: () => void;
  readonly onHome?: () => void;
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
      {/* New topic — LobeHub sidebar + */}
      <button
        type="button"
        className={cn(
          "flex w-full cursor-pointer items-center gap-2 rounded-[var(--radius-md)]",
          "border border-transparent px-2.5 py-2 text-[13px] font-medium text-[var(--text)]",
          "transition-colors hover:bg-[var(--fill-hover)]",
          focusRing,
        )}
        onClick={onNew}
      >
        <LobeIcon icon={MessageSquarePlus} size="sm" className="text-[var(--text-muted)]" />
        开启新话题
      </button>

      {/* 最近话题 section */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mb-1 flex items-center gap-1 px-2.5 py-1">
          <span className="text-[12px] font-medium text-[var(--text-muted)]">最近话题</span>
          {conversations.length > 0 ? (
            <span className="text-[11px] text-[var(--text-faint)]">{conversations.length}</span>
          ) : null}
        </div>

        {conversations.length === 0 ? (
          <div className="px-3 py-8 text-center">
            <p className={cn("m-0 text-xs", mutedText)}>暂无话题</p>
            <p className="m-0 mt-1 text-[11px] text-[var(--text-faint)]">
              开始对话后会出现在这里
            </p>
          </div>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-px p-0">
            {/* Optional default / home-like row */}
            {onHome ? (
              <li>
                <button
                  type="button"
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-2 rounded-[var(--radius-md)]",
                    "border border-transparent px-2.5 py-2 text-left transition-colors",
                    homeActive
                      ? "bg-[var(--fill-hover)] text-[var(--text)]"
                      : "text-[var(--text)] hover:bg-[var(--fill-hover)]/70",
                    focusRing,
                  )}
                  onClick={onHome}
                >
                  <LobeIcon
                    icon={MessageSquareDashed}
                    size="sm"
                    className="shrink-0 text-[var(--text-faint)]"
                  />
                  <span className="min-w-0 flex-1 truncate text-[13px]">默认话题</span>
                  <span className="shrink-0 rounded-[var(--radius-xs)] border border-[var(--border)] px-1 text-[10px] text-[var(--text-faint)]">
                    临时
                  </span>
                </button>
              </li>
            ) : null}

            {conversations.map((conversation) => {
              const active = !homeActive && conversation.id === activeId;
              const updated =
                conversation.turns.at(-1)?.createdAt ?? conversation.createdAt;
              const empty = conversation.turns.length === 0;
              return (
                <li key={conversation.id} className="group relative">
                  <button
                    type="button"
                    className={cn(
                      "flex w-full cursor-pointer items-center gap-2 rounded-[var(--radius-md)]",
                      "border border-transparent px-2.5 py-2 pr-8 text-left transition-colors",
                      active
                        ? "bg-[var(--fill-hover)] text-[var(--text)]"
                        : "text-[var(--text)] hover:bg-[var(--fill-hover)]/70",
                      focusRing,
                    )}
                    onClick={() => onSelect(conversation.id)}
                  >
                    <LobeIcon
                      icon={empty ? MessageSquareDashed : Hash}
                      size="sm"
                      className="shrink-0 text-[var(--text-faint)]"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium leading-snug">
                        {conversation.title || "未命名主题"}
                      </span>
                      <span className="mt-0.5 block text-[11px] text-[var(--text-faint)]">
                        {conversation.turns.length} 轮
                        {updated ? ` · ${formatRelativeTime(updated)}` : ""}
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    className={cn(
                      "absolute top-1/2 right-1 -translate-y-1/2",
                      "inline-flex size-7 cursor-pointer items-center justify-center rounded-[var(--radius-sm)]",
                      "text-[var(--text-faint)] opacity-0 transition-all",
                      "hover:bg-[var(--fill-secondary)] hover:text-[var(--color-danger)]",
                      "group-hover:opacity-100 focus-visible:opacity-100",
                      focusRing,
                    )}
                    aria-label="删除话题"
                    onClick={(ev) => {
                      ev.stopPropagation();
                      onDelete(conversation.id);
                    }}
                  >
                    <LobeIcon icon={Trash2} size="sm" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="mt-auto grid gap-2.5 border-t border-[var(--border-subtle)] pt-3 pb-1">
        <div className="flex items-center justify-between gap-2 px-1.5">
          <LlmBadge available={llmAvailable} />
          <ThemeToggle theme={theme} onChange={onThemeChange} />
        </div>
        <label className="flex cursor-pointer items-center justify-between gap-2 rounded-[var(--radius-md)] px-1.5 py-1 text-xs hover:bg-[var(--fill-hover)]">
          <span className={mutedText}>开发者轨迹</span>
          <Switch.Root
            className={cn(
              "relative h-5 w-9 shrink-0 rounded-full bg-[var(--fill-secondary)] transition-colors",
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
        <label className="flex items-center justify-between gap-2 px-1.5 py-0.5 text-xs">
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
