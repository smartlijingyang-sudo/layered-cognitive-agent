import type { ReactNode } from "react";

/** 对话主区：消息可滚动 + 输入框贴底固定（LobeHub 式布局）。 */
export function ChatMain({
  messages,
  footer,
}: {
  readonly messages: ReactNode;
  readonly footer: ReactNode;
}) {
  return (
    <div className="chat-shell flex min-h-0 flex-1 flex-col">
      <div className="chat-scroll flex-1 overflow-y-auto overflow-x-hidden px-4 py-6 md:px-8">
        {messages}
      </div>
      <div className="chat-composer-bar shrink-0 border-t border-border/60 bg-[var(--composer-bg)] px-4 py-4 backdrop-blur-xl md:px-8">
        {footer}
      </div>
    </div>
  );
}

export function ChatMessages({ children }: { readonly children: ReactNode }) {
  return <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">{children}</div>;
}

export function ChatError({ children }: { readonly children: ReactNode }) {
  return (
    <div className="mx-auto mb-4 w-full max-w-3xl rounded-[var(--radius-md)] border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
      {children}
    </div>
  );
}
