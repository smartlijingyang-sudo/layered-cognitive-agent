import { useCallback, useEffect, useRef, useState } from "react";
import { ModePicker } from "./ModePicker";
import { AttachmentUpload } from "./AttachmentUpload";
import { ArrowUp, Square } from "lucide-react";
import type { LocalAttachment } from "../../domain/generated-file";
import { cn } from "../../lib/cn";
import {
  COMPOSER_ACTION_BLOCK,
  ICON_SIZE,
  ICON_STROKE_BOLD,
  LobeIcon,
} from "../../lib/icons";
import { focusRing } from "../../lib/ui";
import { AgentAvatar } from "../shared/AgentAvatar";

const MAX_TEXTAREA_PX = 320;
/** LobeHub home editor min-height ~88px total chrome; textarea body ~46px+ */
const MIN_TEXTAREA_PX = 56;
/**
 * Browsers (Safari) may fire `compositionend` before the confirming Enter
 * keydown, leaving `isComposing` false. Suppress Enter within this window
 * after composition ends so IME candidate selection never sends the message.
 */
const IME_SETTLE_MS = 100;

export type ComposerLayout = "home" | "topic" | "chat";

export function Composer({
  mode,
  onModeChange,
  onSubmit,
  onStop,
  busy,
  canStop,
  llmAvailable,
  conversationId,
  layout = "chat",
}: {
  readonly mode: string;
  readonly onModeChange: (mode: string) => void;
  readonly onSubmit: (question: string, attachments: readonly LocalAttachment[]) => void;
  readonly onStop: () => void;
  readonly busy: boolean;
  readonly canStop: boolean;
  readonly llmAvailable: boolean | null;
  readonly conversationId?: string;
  /** LobeHub: home = mode in action bar; topic = mode in control bar below. */
  readonly layout?: ComposerLayout;
}) {
  const [question, setQuestion] = useState("");
  const [attachments, setAttachments] = useState<readonly LocalAttachment[]>([]);
  const [dragging, setDragging] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const compositionEndRef = useRef(0);
  const disabled = busy || llmAvailable === false;
  const modeInActionBar = layout === "home" || layout === "chat";
  const modeInControlBar = layout === "topic";

  const resize = useCallback(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(Math.max(el.scrollHeight, MIN_TEXTAREA_PX), MAX_TEXTAREA_PX)}px`;
  }, []);

  useEffect(() => {
    resize();
  }, [question, resize]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      // IME composition (CJK input): Enter confirms the candidate, it must not send.
      const justFinishedComposing =
        Date.now() - compositionEndRef.current < IME_SETTLE_MS;
      if (event.nativeEvent.isComposing || justFinishedComposing) return;
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

  const onDropFiles = (files: FileList | null) => {
    setDragging(false);
    if (!files?.length || disabled) return;
    const added: LocalAttachment[] = Array.from(files).map((file) => ({
      id: `att-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      name: file.name,
      mimeType: file.type || "application/octet-stream",
      sizeBytes: file.size,
      status: "local" as const,
      file,
    }));
    setAttachments((prev) => [...prev, ...added]);
  };

  const placeholder =
    llmAvailable === false
      ? "LLM 未配置，请在服务端设置 LLM_API_KEY"
      : "提问、搜索或头脑风暴。@ 召唤其他智能体加入。";

  return (
    <div
      className={cn(
        "mx-auto flex w-full flex-col gap-2",
        layout === "home" ? "lobe-home-column" : "max-w-[var(--chat-max-width)]",
      )}
    >
      <div
        className={cn(
          "lobe-composer relative rounded-[20px] border bg-[var(--composer-bg)]",
          "shadow-[0_12px_32px_rgba(0,0,0,0.04)] backdrop-blur-xl transition-all duration-200",
          dragging
            ? "border-[var(--color-info)] ring-2 ring-[var(--color-info)]/20"
            : "border-[var(--border)] focus-within:border-[var(--text-faint)] focus-within:shadow-[var(--shadow-popover)]",
        )}
        data-testid="chat-input"
        onDragEnter={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          onDropFiles(e.dataTransfer.files);
        }}
      >
        {dragging ? (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-[var(--radius-2xl)] bg-[color-mix(in_srgb,var(--color-info)_8%,transparent)]">
            <span className="text-sm font-medium text-[var(--color-info)]">松开以添加附件</span>
          </div>
        ) : null}

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
          ref={taRef}
          className={cn(
            "block w-full resize-none border-0 bg-transparent px-4 pt-3.5 pb-2",
            "text-[0.875rem] leading-[1.4] text-[var(--text)] outline-none",
            "placeholder:text-[var(--text-faint)] disabled:cursor-not-allowed disabled:opacity-50",
          )}
          style={{ minHeight: MIN_TEXTAREA_PX, maxHeight: MAX_TEXTAREA_PX }}
          rows={1}
          placeholder={placeholder}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionEnd={() => {
            compositionEndRef.current = Date.now();
          }}
          disabled={disabled}
        />

        <div className="flex items-center justify-between gap-2 px-2 pb-2 pr-2">
          <div className="flex min-w-0 flex-1 items-center gap-0.5 pl-1.5">
            <div className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto">
              {layout === "topic" ? (
                <span className="inline-flex shrink-0 items-center justify-center p-0.5">
                  <AgentAvatar size={20} title="LCA" />
                </span>
              ) : null}
              {modeInActionBar ? (
                <ModePicker value={mode} onChange={onModeChange} disabled={busy} />
              ) : null}
            </div>
            <AttachmentUpload
              attachments={attachments}
              onChange={setAttachments}
              conversationId={conversationId}
              disabled={disabled}
              autoUpload={false}
              compact
            />
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {canStop ? (
              <button
                type="button"
                className={cn(
                  "inline-flex cursor-pointer items-center justify-center rounded-full",
                  "border border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--text)]",
                  "transition-colors hover:bg-[var(--fill-hover)]",
                  focusRing,
                )}
                style={{ width: COMPOSER_ACTION_BLOCK - 4, height: COMPOSER_ACTION_BLOCK - 4 }}
                onClick={onStop}
                aria-label="停止生成"
              >
                <LobeIcon icon={Square} size="xs" fill="currentColor" />
              </button>
            ) : (
              <button
                type="button"
                className={cn(
                  "inline-flex cursor-pointer items-center justify-center rounded-full border-0",
                  "bg-[var(--accent)] text-[var(--accent-fg)] shadow-sm",
                  "transition-transform active:scale-95",
                  "disabled:cursor-not-allowed disabled:opacity-30 disabled:active:scale-100",
                  focusRing,
                )}
                style={{ width: COMPOSER_ACTION_BLOCK - 4, height: COMPOSER_ACTION_BLOCK - 4 }}
                disabled={disabled || !question.trim()}
                onClick={send}
                aria-label="发送"
              >
                <LobeIcon
                  icon={ArrowUp}
                  size={ICON_SIZE.md}
                  strokeWidth={ICON_STROKE_BOLD}
                />
              </button>
            )}
          </div>
        </div>
      </div>

      {modeInControlBar ? (
        <div className="flex items-center justify-between gap-2 px-1">
          <ModePicker value={mode} onChange={onModeChange} disabled={busy} variant="chat" />
        </div>
      ) : null}

      <p className="m-0 text-center text-[10px] leading-none text-[var(--text-faint)]">
        LCA · 历史保存在本机浏览器
        {attachments.length > 0 ? ` · ${attachments.length} 个附件` : ""}
      </p>
    </div>
  );
}
