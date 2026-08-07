import * as Dialog from "@radix-ui/react-dialog";
import { ALL_MODES, MODE_HAS_LEAD, MODE_HELP, type Mode } from "../../contracts/catalog.generated";
import { X } from "lucide-react";
import { cn } from "../../lib/cn";
import { elevatedSurface, focusRing, iconButton, inputField, mutedText } from "../../lib/ui";

export function ModePicker({
  value,
  onChange,
  disabled,
}: {
  readonly value: string;
  readonly onChange: (mode: string) => void;
  readonly disabled?: boolean;
}) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className={cn(inputField, "max-w-md cursor-pointer text-left")}
          disabled={disabled}
        >
          <span className="block font-semibold">{value}</span>
          <span className={cn("block text-sm", mutedText)}>
            {MODE_HELP[value as Mode] ?? "选择协作模式"}
          </span>
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/45" />
        <Dialog.Content
          className={cn(
            elevatedSurface,
            "fixed top-1/2 left-1/2 z-50 max-h-[calc(100vh-2rem)] w-[min(720px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-auto p-4 shadow-xl",
            focusRing,
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <Dialog.Title className="text-base font-semibold">协作模式</Dialog.Title>
            <Dialog.Close asChild>
              <button type="button" className={iconButton} aria-label="关闭">
                <X size={16} />
              </button>
            </Dialog.Close>
          </div>
          <div className="mt-3 grid gap-2">
            {ALL_MODES.map((mode) => {
              const selected = mode === value;
              return (
                <button
                  key={mode}
                  type="button"
                  className={cn(
                    "cursor-pointer rounded-[var(--radius-md)] border bg-surface p-3 text-left text-inherit",
                    selected ? "border-accent" : "border-border hover:border-accent/50",
                    focusRing,
                  )}
                  onClick={() => onChange(mode)}
                >
                  <div className="flex items-center gap-2">
                    <strong>{mode}</strong>
                    {MODE_HAS_LEAD[mode] ? (
                      <span className="rounded-full border border-border px-1.5 py-0.5 text-xs text-team">
                        有主导
                      </span>
                    ) : null}
                    {mode === "solo" ? (
                      <span className="rounded-full border border-border px-1.5 py-0.5 text-xs text-event">
                        单 Agent
                      </span>
                    ) : null}
                  </div>
                  <p className={cn("m-0 mt-1 text-sm", mutedText)}>{MODE_HELP[mode]}</p>
                </button>
              );
            })}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
