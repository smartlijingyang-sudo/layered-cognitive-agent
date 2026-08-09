/**
 * LobeHub home right panel (click left Home):
 * - Agent select row: 32×32 square /avatars/lobe-ai.png + title + ChevronsUpDown
 * - Welcome lines
 * - Input is the shared Composer docked below (ChatMain footer)
 */
import { ChevronsUpDown } from "lucide-react";
import { AgentAvatar } from "../shared/AgentAvatar";
import { cn } from "../../lib/cn";
import { LobeIcon } from "../../lib/icons";
import { focusRing } from "../../lib/ui";

const WELCOME_LINES = ["今天也辛苦啦", "嗨，我在呢"] as const;

export function HomeWelcome({
  agentTitle = "LCA",
  onAgentClick,
}: {
  readonly agentTitle?: string;
  /** Opens mode / agent picker — optional. */
  readonly onAgentClick?: () => void;
}) {
  return (
    <div className="lobe-home-column lobe-home-panel">
      {/* Agent select — matches LobeHub home AgentSelect trigger */}
      <div className="flex flex-col gap-2">
        <button
          type="button"
          className={cn(
            "group flex w-fit cursor-pointer items-center gap-2 rounded-[var(--radius-md)] p-1",
            "border-0 bg-transparent text-left transition-colors",
            "hover:bg-[var(--fill-hover)]",
            focusRing,
          )}
          onClick={onAgentClick}
          aria-haspopup="dialog"
        >
          <AgentAvatar size={32} title={agentTitle} />
          <span className="text-[16px] font-semibold tracking-tight text-[var(--text)]">
            {agentTitle}
          </span>
          <span
            className={cn(
              "agent-select-chevron inline-flex size-6 items-center justify-center rounded-[6px]",
              "text-[var(--text-faint)] opacity-0 transition-opacity",
              "group-hover:opacity-100 group-focus-visible:opacity-100",
            )}
          >
            <LobeIcon icon={ChevronsUpDown} size="sm" />
          </span>
        </button>

        {/* Welcome copy — LobeHub height ~3.2em / line-height 1.6 */}
        <div
          className="lobe-home-welcome-text whitespace-pre-wrap break-words ps-[5px] text-[16px] leading-[1.6] text-[var(--text)]"
          style={{ minHeight: "3.2em" }}
        >
          {WELCOME_LINES.join("\n")}
        </div>
      </div>
    </div>
  );
}
