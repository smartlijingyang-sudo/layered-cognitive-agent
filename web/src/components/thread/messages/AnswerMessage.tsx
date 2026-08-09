import { MarkdownContent } from "../../shared/MarkdownContent";
import type { Message } from "../../../projectors/message-types";

export function AnswerMessage({ message }: { readonly message: Message }) {
  return (
    <div className="lobe-final-answer min-w-0">
      <MarkdownContent text={message.content} streaming={message.streaming} />
    </div>
  );
}
