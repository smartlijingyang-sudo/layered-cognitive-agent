import { Users } from "lucide-react";
import type { Message } from "../../../projectors/message-types";
import { cn } from "../../../lib/cn";
import { LobeIcon } from "../../../lib/icons";
import { mutedText } from "../../../lib/ui";

export function CastingMessage({ message }: { readonly message: Message }) {
  const meta = message.metadata;

  if (message.status === "running") {
    return (
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
        <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
          <span className="text-[var(--text-muted)]">
            <LobeIcon icon={Users} size="sm" />
          </span>
          ◎ 智能选角
        </div>
        <p className={cn("m-0 mt-1 text-sm whitespace-pre-wrap", mutedText)}>
          {meta?.objectivePreview || "正在分析问题并挑选角色…"}
        </p>
      </div>
    );
  }

  if (message.status === "error") {
    return (
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
        <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
          <span className="text-[var(--color-danger)]">
            <LobeIcon icon={Users} size="sm" />
          </span>
          ✗ 组队失败
        </div>
        <p className={cn("m-0 mt-1 text-sm whitespace-pre-wrap", mutedText)}>
          {meta?.errorMessage || message.content}
        </p>
      </div>
    );
  }

  const roles = meta?.selectedRoles?.join("、") ?? "";
  const body = [
    meta?.governanceKind ? `协作方式：${meta.governanceKind}` : null,
    meta?.leadRole ? `主导：${meta.leadRole}` : null,
    roles ? `成员：${roles}` : null,
    meta?.rationale || null,
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5">
      <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
        <span className="text-[var(--color-success)]">
          <LobeIcon icon={Users} size="sm" />
        </span>
        ✓ 组队完成
      </div>
      {body ? (
        <p className={cn("m-0 mt-1 text-sm whitespace-pre-wrap", mutedText)}>{body}</p>
      ) : null}
    </div>
  );
}
