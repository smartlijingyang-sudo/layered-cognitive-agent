import { useState } from "react";
import { ModePicker } from "./ModePicker";
import { AttachmentUpload } from "./AttachmentUpload";
import { ArrowUp, Square } from "lucide-react";
import { AUTO_MODE_KEY } from "../../contracts/modes.generated";
import type { LocalAttachment } from "../../domain/generated-file";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";

export function Composer({
  mode,
  onModeChange,
  onSubmit,
  onStop,
  busy,
  canStop,
  llmAvailable,
  conversationId,
}: {
  readonly mode: string;
  readonly onModeChange: (mode: string) => void;
  readonly onSubmit: (question: string, attachments: readonly LocalAttachment[]) => void;
  readonly onStop: () => void;
  readonly busy: boolean;
  readonly canStop: boolean;
  readonly llmAvailable: boolean | null;
  readonly conversationId?: string;
}) {
  const [question, setQuestion] = useState("");
  const [attachments, setAttachments] = useState<readonly LocalAttachment[]>([]);
  const disabled = busy || llmAvailable === false;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!disabled && question.trim()) {
        onSubmit(question.trim(), attachments);
        setQuestion("");
        setAttachments([]);
      }
    }
  };

  const send = () => {
    if (disabled || !question.trim()) return;
    onSubmit(question.trim(), attachments);
    setQuestion("");
    setAttachments([]);
  };

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-2">
      <div
        className={cn(
          "rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)]",
          "shadow-[var(--shadow-popover)] transition-shadow",
          "focus-within:border-[var(--text-faint)] focus-within:shadow-[var(--shadow-modal)]",
        )}
      >
        {attachments.length > 0 ? (
          <div className="border-b border-[var(--border-subtle)] px-3 pt-3">
            <AttachmentUpload
              attachments={attachments}
              onChange={setAttachments}
              conversationId={conversationId}
              disabled={disabled}
              autoUpload={false}
            />
          </div>
        ) : null}

        <textarea
          className={cn(
            "block w-full resize-none border-0 bg-transparent px-4 py-3.5",
            "text-[0.9375rem] leading-relaxed text-[var(--text)] outline-none",
            "placeholder:text-[var(--text-faint)] disabled:cursor-not-allowed disabled:opacity-50",
            "min-h-[3.25rem] max-h-[12rem]",
          )}
          rows={2}
          placeholder={
            llmAvailable === false
              ? "LLM 未配置，请在服务端设置 LLM_API_KEY"
              : mode === AUTO_MODE_KEY
                ? "描述问题，Enter 发送 · Shift+Enter 换行"
                : "输入问题，Enter 发送"
          }
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />

        {/* Action bar — LobeHub ChatInput bottom row */}
        <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5">
          <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto">
            <ModePicker value={mode} onChange={onModeChange} disabled={busy} />
            <AttachmentUpload
              attachments={attachments}
              onChange={setAttachments}
              conversationId={conversationId}
              disabled={disabled}
              autoUpload={false}
              compact
            />
          </div>
          <div className="shrink-0">
            {canStop ? (
              <button
                type="button"
                className={cn(
                  "inline-flex size-9 cursor-pointer items-center justify-center rounded-full",
                  "border border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--text)]",
                  "hover:bg-[var(--fill-hover)]",
                  focusRing,
                )}
                onClick={onStop}
                aria-label="停止生成"
              >
                <Square size={12} fill="currentColor" />
              </button>
            ) : (
              <button
                type="button"
                className={cn(
                  "inline-flex size-9 cursor-pointer items-center justify-center rounded-full border-0",
                  "bg-[var(--accent)] text-[var(--accent-fg)] shadow-sm",
                  "disabled:cursor-not-allowed disabled:opacity-35",
                  focusRing,
                )}
                disabled={disabled || !question.trim()}
                onClick={send}
                aria-label="发送"
              >
                <ArrowUp size={16} strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>
      </div>
      <p className="m-0 text-center text-[10px] text-[var(--text-faint)]">
        LCA · 历史保存在本机
        {attachments.length > 0 ? " · 含附件" : ""}
      </p>
    </div>
  );
}
