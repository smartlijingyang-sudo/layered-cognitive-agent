import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

/** 对话主区：消息可滚动 + 输入框贴底（LobeHub Chat / Home 布局）。 */
export function ChatMain({
  messages,
  footer,
  emptyCentered = false,
  homeLayout = false,
  homeColumn = false,
}: {
  readonly messages: ReactNode;
  readonly footer: ReactNode;
  /** Empty thread: center content (legacy). Prefer homeLayout for LobeHub home. */
  readonly emptyCentered?: boolean;
  /**
   * LobeHub home: padding-block 44px 16vh, content top-aligned, max-width column.
   */
  readonly homeLayout?: boolean;
  /** Home view: composer shares `.lobe-home-column` width/padding with welcome block. */
  readonly homeColumn?: boolean;
}) {
  return (
    <div className="chat-shell relative flex min-h-0 flex-1 flex-col bg-[var(--chat-bg)]">
      <div
        className={cn(
          "chat-scroll flex-1 overflow-y-auto overflow-x-hidden",
          homeLayout
            ? "flex flex-col px-0 pt-11 pb-[8vh] md:pt-11"
            : emptyCentered
              ? "flex flex-col justify-center px-4 py-8 md:px-8"
              : "px-3 py-5 md:px-6 md:py-7",
        )}
      >
        {messages}
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-[var(--composer-stack-height,7.5rem)] h-10 bg-gradient-to-t from-[var(--chat-bg)] to-transparent" />

      <div
        className={cn(
          "lobe-composer-dock shrink-0 pb-3 pt-0 md:pb-4",
          homeColumn ? "px-0" : "px-3 md:px-6",
          "bg-gradient-to-t from-[var(--chat-bg)] from-60% via-[var(--chat-bg)] to-transparent",
        )}
      >
        {footer}
      </div>
    </div>
  );
}

export function ChatMessages({ children }: { readonly children: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-[var(--chat-max-width)] flex-col gap-8">
      {children}
    </div>
  );
}

export function ChatError({ children }: { readonly children: ReactNode }) {
  return (
    <div
      className={cn(
        "mx-auto mb-3 w-full max-w-[var(--chat-max-width)]",
        "rounded-[var(--radius-lg)] border border-[var(--color-danger)]/25",
        "bg-[color-mix(in_srgb,var(--color-danger)_8%,transparent)]",
        "px-4 py-3 text-sm text-[var(--color-danger)]",
      )}
      role="alert"
    >
      {children}
    </div>
  );
}
