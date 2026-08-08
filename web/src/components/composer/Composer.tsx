import { useState } from "react";
import { ModePicker } from "./ModePicker";
import { ArrowUp, Square } from "lucide-react";
import { AUTO_MODE_KEY } from "../../contracts/modes.generated";
import { btnPrimary, btnSecondary } from "../../lib/ui";
import { cn } from "../../lib/cn";

export function Composer({
  mode,
  onModeChange,
  onSubmit,
  onStop,
  busy,
  canStop,
  llmAvailable,
}: {
  readonly mode: string;
  readonly onModeChange: (mode: string) => void;
  readonly onSubmit: (question: string) => void;
  readonly onStop: () => void;
  readonly busy: boolean;
  readonly canStop: boolean;
  readonly llmAvailable: boolean | null;
}) {
  const [question, setQuestion] = useState("");
  const disabled = busy || llmAvailable === false;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!disabled && question.trim()) {
        onSubmit(question.trim());
        setQuestion("");
      }
    }
  };

  const send = () => {
    if (disabled || !question.trim()) return;
    onSubmit(question.trim());
    setQuestion("");
  };

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-3">
      <ModePicker value={mode} onChange={onModeChange} disabled={busy} />
      <div
        className={cn(
          "relative rounded-[var(--radius-xl)] border border-border/80 bg-surface",
          "shadow-[0_2px_12px_color-mix(in_srgb,var(--text)_4%,transparent)]",
          "ring-1 ring-border/30 transition-shadow focus-within:ring-accent/35",
        )}
      >
        <textarea
          className={cn(
            "block w-full resize-none border-0 bg-transparent px-4 py-3.5 pr-14",
            "text-[0.9375rem] leading-relaxed text-text outline-none",
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
        <div className="absolute bottom-2.5 right-2.5">
          {canStop ? (
            <button
              type="button"
              className={cn(btnSecondary, "size-9 justify-center rounded-full p-0")}
              onClick={onStop}
              aria-label="停止生成"
            >
              <Square size={14} />
            </button>
          ) : (
            <button
              type="button"
              className={cn(
                btnPrimary,
                "size-9 justify-center rounded-full p-0 shadow-sm",
                "disabled:opacity-40",
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
      <p className="m-0 text-center text-[11px] text-[var(--text-faint)]">
        LCA 可展示团队协作过程 · 历史保存在本机
      </p>
    </div>
  );
}
