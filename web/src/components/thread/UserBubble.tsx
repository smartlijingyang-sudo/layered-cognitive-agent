import type { Turn } from "../../domain/conversation";

export function UserBubble({ turn }: { readonly turn: Turn }) {
  return (
    <article className="bubble user-bubble">
      <header className="bubble-meta">你 · {turn.mode}</header>
      <p>{turn.question}</p>
    </article>
  );
}
