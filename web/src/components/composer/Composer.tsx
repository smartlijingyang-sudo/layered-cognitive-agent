import { useState } from "react";
import { ModePicker } from "./ModePicker";
import { SendHorizontal, Square } from "lucide-react";
import { btnPrimary, btnSecondary, inputField } from "../../lib/ui";
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

  return (
    <div className="mt-auto flex flex-col gap-2.5 border-t border-border pt-4">
      <div className="flex flex-wrap gap-3">
        <ModePicker value={mode} onChange={onModeChange} disabled={busy} />
      </div>
      <textarea
        className={cn(inputField, "min-h-[5.5rem] resize-y")}
        rows={3}
        placeholder={
          llmAvailable === false
            ? "LLM 未配置，请在服务端设置 LLM_API_KEY"
            : "输入问题，Enter 发送，Shift+Enter 换行"
        }
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
      />
      <div className="flex justify-end">
        {canStop ? (
          <button type="button" className={btnSecondary} onClick={onStop}>
            <Square size={14} /> 停止生成
          </button>
        ) : (
          <button
            type="button"
            className={btnPrimary}
            disabled={disabled || !question.trim()}
            onClick={() => {
              onSubmit(question.trim());
              setQuestion("");
            }}
          >
            <SendHorizontal size={14} /> {busy ? "生成中…" : "发送"}
          </button>
        )}
      </div>
    </div>
  );
}
