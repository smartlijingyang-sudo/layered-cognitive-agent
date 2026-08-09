/**
 * LobeHub CheckboxItem row inside Plus attachments submenu.
 */
import type { LocalAttachment } from "../../domain/generated-file";
import { fileIconKind } from "../../lib/file-mime-icon";
import { cn } from "../../lib/cn";
import {
  COMPOSER_MENU_ICON_PX,
  composerMenuRowInteractive,
  ComposerMenuIcon,
} from "./composer-menu";
import {
  File,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { LobeIcon } from "../../lib/icons";

const KIND_ICON: Record<string, LucideIcon> = {
  image: FileImage,
  pdf: FileText,
  code: FileCode,
  table: FileSpreadsheet,
  text: FileText,
  archive: FileArchive,
  html: FileCode,
  audio: FileAudio,
  video: FileVideo,
  file: File,
};

const TRUNCATE_TAIL = 8;

function MiddleEllipsis({ text }: { readonly text: string }) {
  if (text.length <= TRUNCATE_TAIL + 1) {
    return <span className="truncate">{text}</span>;
  }
  const head = text.slice(0, -TRUNCATE_TAIL);
  const tail = text.slice(-TRUNCATE_TAIL);
  return (
    <span className="flex min-w-0 overflow-hidden">
      <span className="min-w-0 truncate">{head}</span>
      <span className="shrink-0 whitespace-nowrap">{tail}</span>
    </span>
  );
}

function AttachmentFileIcon({ att }: { readonly att: LocalAttachment }) {
  const kind = fileIconKind(att.mimeType, att.name);
  const Icon = KIND_ICON[kind] ?? File;
  return <LobeIcon icon={Icon} size={COMPOSER_MENU_ICON_PX} />;
}

function MenuCheckbox({ checked }: { readonly checked: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex size-[18px] shrink-0 items-center justify-center rounded-[4px] border",
        checked
          ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-fg)]"
          : "border-[var(--border)] bg-[var(--surface)]",
      )}
      aria-hidden
    >
      {checked ? (
        <svg viewBox="0 0 12 12" className="size-2.5" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M2 6l3 3 5-5" />
        </svg>
      ) : null}
    </span>
  );
}

export function AttachmentMenuItem({
  att,
  onToggle,
}: {
  readonly att: LocalAttachment;
  readonly onToggle: (id: string) => void;
}) {
  const attached = att.status !== "error";

  return (
    <button
      type="button"
      role="menuitemcheckbox"
      aria-checked={attached}
      className={composerMenuRowInteractive}
      data-testid="attachment-menu-item"
      title={att.name}
      onClick={() => onToggle(att.id)}
    >
      <ComposerMenuIcon>
        <AttachmentFileIcon att={att} />
      </ComposerMenuIcon>
      <span className="flex min-w-0 flex-1 items-center justify-between gap-6">
        <span className="min-w-0 flex-1 overflow-hidden">
          <MiddleEllipsis text={att.name} />
        </span>
        <MenuCheckbox checked={attached} />
      </span>
    </button>
  );
}
