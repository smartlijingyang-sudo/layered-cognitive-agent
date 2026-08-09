import type { ReactNode } from "react";

/** 对话主区：消息可滚动 + 输入框贴底（LobeHub Chat 布局）。 */
export function ChatMain({
  messages,
  footer,
}: {
  readonly messages: ReactNode;
  readonly footer: ReactNode;
}) {
  return (
    <div className="chat-shell flex min-h-0 flex-1 flex-col bg-[var(--chat-bg)]">
      <div className="chat-scroll flex-1 overflow-y-auto overflow-x-hidden px-3 py-5 md:px-6 md:py-6">
        {messages}
      </div>
      <div
        className={cnComposerBar(
          "shrink-0 px-3 pb-4 pt-1 md:px-6",
          "bg-gradient-to-t from-[var(--chat-bg)] via-[var(--chat-bg)] to-transparent",
        )}
      >
        {footer}
      </div>
    </div>
  );
}

function cnComposerBar(...parts: string[]): string {
  return parts.filter(Boolean).join(" ");
}

export function ChatMessages({ children }: { readonly children: ReactNode }) {
  return <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">{children}</div>;
}

export function ChatError({ children }: { readonly children: ReactNode }) {
  return (
    <div
      className={
        "mx-auto mb-4 w-full max-w-3xl rounded-[var(--radius-lg)] border border-[var(--color-danger)]/30 " +
        "bg-[color-mix(in_srgb,var(--color-danger)_8%,transparent)] px-4 py-3 text-sm text-[var(--color-danger)]"
      }
    >
      {children}
    </div>
  );
}
