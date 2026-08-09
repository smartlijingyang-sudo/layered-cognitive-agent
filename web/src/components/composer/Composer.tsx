import { useCallback, useEffect, useRef, useState } from "react";
import { ModePicker } from "./ModePicker";
import { AttachmentUpload } from "./AttachmentUpload";
import {
  COMPOSER_ACTION_BAR_CLASS,
  ComposerSendButton,
  ComposerStopButton,
} from "./composer-action-bar";
import type { LocalAttachment } from "../../domain/generated-file";
import { cn } from "../../lib/cn";
import { AgentAvatar } from "../shared/AgentAvatar";

const MAX_TEXTAREA_PX = 320;
/** LobeHub home editor min-height ~88px total chrome; textarea body ~46px+ */
const MIN_TEXTAREA_PX = 56;
/** Default prompt when user sends attachments without text. */
export const ATTACHMENT_ONLY_QUESTION = "请阅读并分析以上附件。";
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
  const dragDepthRef = useRef(0);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const compositionEndRef = useRef(0);
  const busyOnly = busy;
  const sendBlocked = busy || llmAvailable === false;
  const canAddAttachments = !busyOnly;
  const canSend =
    !sendBlocked && (question.trim().length > 0 || attachments.length > 0);
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
      if (canSend) {
        onSubmit(question.trim() || ATTACHMENT_ONLY_QUESTION, attachments);
        setQuestion("");
        setAttachments([]);
      }
    }
  };

  const send = () => {
    if (!canSend) return;
    onSubmit(question.trim() || ATTACHMENT_ONLY_QUESTION, attachments);
    setQuestion("");
    setAttachments([]);
  };

  const onDropFiles = (files: FileList | null) => {
    dragDepthRef.current = 0;
    setDragging(false);
    if (!files?.length || !canAddAttachments) return;
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
          if (!canAddAttachments) return;
          dragDepthRef.current += 1;
          setDragging(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (canAddAttachments) e.dataTransfer.dropEffect = "copy";
        }}
        onDragLeave={() => {
          dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
          if (dragDepthRef.current === 0) setDragging(false);
        }}
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
          <div className="px-2 py-2">
            <AttachmentUpload
              attachments={attachments}
              onChange={setAttachments}
              conversationId={conversationId}
              disabled={!canAddAttachments}
              autoUpload={Boolean(conversationId)}
              onDropFiles={onDropFiles}
            />
          </div>
        ) : null}

        <textarea
          ref={taRef}
          className={cn(
            "block w-full resize-none border-0 bg-transparent px-3 pt-2 pb-0",
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
          disabled={sendBlocked}
        />

        <div className={COMPOSER_ACTION_BAR_CLASS}>
          <div className="flex min-h-8 min-w-0 items-center gap-1 overflow-x-auto">
            {layout === "topic" ? (
              <span className="inline-flex shrink-0 items-center justify-center">
                <AgentAvatar size={20} title="LCA" />
              </span>
            ) : null}
            {modeInActionBar ? (
              <ModePicker
                value={mode}
                onChange={onModeChange}
                disabled={busy}
                menuPlacement={layout === "home" ? "bottomLeft" : "topLeft"}
              />
            ) : null}
            <AttachmentUpload
              attachments={attachments}
              onChange={setAttachments}
              conversationId={conversationId}
              disabled={!canAddAttachments}
              autoUpload={Boolean(conversationId)}
              compact
              menuPlacement={layout === "home" ? "bottomLeft" : "topLeft"}
              onDropFiles={onDropFiles}
            />
          </div>
          <div className="inline-flex items-center">
            {canStop ? (
              <ComposerStopButton onClick={onStop} />
            ) : (
              <ComposerSendButton disabled={!canSend} onClick={send} />
            )}
          </div>
        </div>
      </div>

      {modeInControlBar ? (
        <div className="flex items-center justify-between gap-2 px-1">
          <ModePicker
            value={mode}
            onChange={onModeChange}
            disabled={busy}
            variant="chat"
            menuPlacement="topLeft"
          />
        </div>
      ) : null}

      <p className="m-0 text-center text-[10px] leading-none text-[var(--text-faint)]">
        LCA · 历史保存在本机浏览器
        {attachments.length > 0 ? ` · ${attachments.length} 个附件` : ""}
      </p>
    </div>
  );
}
