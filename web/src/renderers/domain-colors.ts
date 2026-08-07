import type { VocabDomain } from "../contracts";

export const DOMAIN_COLORS: Record<VocabDomain, string> = {
  run: "#0d9488",
  team: "#7c3aed",
  cognitive: "#2563eb",
  resource: "#d97706",
  event: "#64748b",
};

export function domainColor(domain?: VocabDomain): string {
  return domain ? DOMAIN_COLORS[domain] : DOMAIN_COLORS.event;
}
