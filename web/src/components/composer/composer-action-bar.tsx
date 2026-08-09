import { cn } from "../../lib/cn";
import { COMPOSER_ACTION_BLOCK } from "../../lib/icons";
import { focusRing } from "../../lib/ui";
import { SendIcon } from "./SendIcon";

/** 32×32 circle — matches Plus ActionIcon blockSize. */
export const composerActionCircle = cn(
  "inline-flex shrink-0 items-center justify-center rounded-full",
  focusRing,
);

export const COMPOSER_ACTION_BAR_CLASS = cn(
  "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-1",
  "p-1 pr-2",
);

export function ComposerSendButton({
  disabled,
  onClick,
}: {
  readonly disabled?: boolean;
  readonly onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        composerActionCircle,
        "cursor-pointer border-0 bg-[var(--accent)] text-[var(--accent-fg)] shadow-sm",
        "transition-transform active:scale-95",
        "disabled:cursor-not-allowed disabled:opacity-30 disabled:active:scale-100",
      )}
      style={{ width: COMPOSER_ACTION_BLOCK, height: COMPOSER_ACTION_BLOCK }}
      disabled={disabled}
      onClick={onClick}
      aria-label="发送"
    >
      <SendIcon size={14} />
    </button>
  );
}

export function ComposerStopButton({ onClick }: { readonly onClick: () => void }) {
  return (
    <button
      type="button"
      className={cn(
        composerActionCircle,
        "cursor-pointer border border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--text)]",
        "transition-colors hover:bg-[var(--fill-hover)]",
      )}
      style={{ width: COMPOSER_ACTION_BLOCK, height: COMPOSER_ACTION_BLOCK }}
      onClick={onClick}
      aria-label="停止生成"
    >
      <span className="inline-block size-2.5 rounded-[2px] bg-current" />
    </button>
  );
}
