import * as Dialog from "@radix-ui/react-dialog";
import { ALL_MODES, MODE_HAS_LEAD, MODE_HELP, type Mode } from "../../contracts/catalog.generated";
import { X } from "lucide-react";

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
        <button type="button" className="mode-trigger" disabled={disabled}>
          <span className="mode-trigger-label">{value}</span>
          <span className="mode-trigger-hint">{MODE_HELP[value as Mode] ?? "选择协作模式"}</span>
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content mode-dialog">
          <div className="dialog-header">
            <Dialog.Title>协作模式</Dialog.Title>
            <Dialog.Close asChild>
              <button type="button" className="icon-button" aria-label="关闭">
                <X size={16} />
              </button>
            </Dialog.Close>
          </div>
          <div className="mode-list">
            {ALL_MODES.map((mode) => (
              <button
                key={mode}
                type="button"
                className={`mode-item ${mode === value ? "selected" : ""}`}
                onClick={() => onChange(mode)}
              >
                <div className="mode-item-head">
                  <strong>{mode}</strong>
                  {MODE_HAS_LEAD[mode] ? <span className="mode-tag lead">有主导</span> : null}
                  {mode === "solo" ? <span className="mode-tag solo">单 Agent</span> : null}
                </div>
                <p>{MODE_HELP[mode]}</p>
              </button>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
