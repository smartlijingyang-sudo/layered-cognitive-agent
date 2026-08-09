/**
 * LobeHub empty topic (开启新话题):
 * - flex spacer pushes welcome block toward the input
 * - 64×64 avatar, bold title, markdown opening line
 */
import { AgentAvatar } from "../shared/AgentAvatar";
import { MarkdownContent } from "../shared/MarkdownContent";

const OPENING = "你好，我是 **LCA**。从一句话开始就行——决定权在你";

export function TopicWelcome({
  agentTitle = "LCA",
}: {
  readonly agentTitle?: string;
}) {
  return (
    <div className="lobe-topic-panel mx-auto flex h-full min-h-0 w-full max-w-[min(960px,100%)] flex-col px-4 md:px-4">
      <div className="flex-1" aria-hidden />
      <div
        className="flex w-full flex-col gap-3 pb-[max(4vh,16px)]"
        style={{ paddingBottom: "max(4vh, 16px)" }}
      >
        <AgentAvatar size={64} title={agentTitle} />
        <div className="text-[24px] font-bold leading-tight tracking-tight text-[var(--text)]">
          {agentTitle}
        </div>
        <div className="lobe-topic-welcome-markdown w-full max-w-[640px] text-[15px] leading-[1.6] text-[var(--text)]">
          <MarkdownContent text={OPENING} />
        </div>
      </div>
    </div>
  );
}
