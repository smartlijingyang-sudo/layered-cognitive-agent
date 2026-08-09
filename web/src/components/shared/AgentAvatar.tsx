/**
 * LobeHub real avatar image:
 *   <img alt="avatar" height="32" loading="lazy" width="32" src="/avatars/lobe-ai.png">
 */
import { cn } from "../../lib/cn";

/** Served from `web/public/avatars/lobe-ai.png` (same asset as LobeHub inbox). */
export const DEFAULT_AGENT_AVATAR = "/avatars/lobe-ai.png";

export function AgentAvatar({
  size = 32,
  src = DEFAULT_AGENT_AVATAR,
  className,
  alt = "avatar",
  title = "LCA",
  shape = "square",
}: {
  readonly size?: number;
  readonly src?: string;
  readonly className?: string;
  readonly alt?: string;
  readonly title?: string;
  readonly shape?: "square" | "circle";
}) {
  // LobeHub square avatar radius ≈ 6–8 at 32px
  const radius = shape === "circle" ? size / 2 : Math.max(6, Math.round(size * 0.2));

  return (
    <span
      className={cn(
        "lobe-agent-avatar inline-flex shrink-0 overflow-hidden",
        className,
      )}
      style={{
        width: size,
        height: size,
        minWidth: size,
        minHeight: size,
        borderRadius: radius,
        background: "var(--surface-elevated)",
        boxShadow: "0 0 0 1px color-mix(in srgb, var(--text) 8%, transparent)",
      }}
      data-testid="agent-avatar"
    >
      <img
        alt={alt}
        title={title}
        src={src}
        width={size}
        height={size}
        loading="lazy"
        decoding="async"
        draggable={false}
        style={{
          width: size,
          height: size,
          display: "block",
          objectFit: "cover",
          borderRadius: radius,
        }}
      />
    </span>
  );
}
