import { useState } from "react";
import { ModePicker } from "./ModePicker";
import type { TrackChoice } from "../../api/runs";
import { SendHorizontal, Square } from "lucide-react";

export function Composer({
  mode,
  track,
  onModeChange,
  onTrackChange,
  onSubmit,
  onStop,
  busy,
  canStop,
}: {
  readonly mode: string;
  readonly track: TrackChoice;
  readonly onModeChange: (mode: string) => void;
  readonly onTrackChange: (track: TrackChoice) => void;
  readonly onSubmit: (question: string) => void;
  readonly onStop: () => void;
  readonly busy: boolean;
  readonly canStop: boolean;
}) {
  const [question, setQuestion] = useState("");

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!busy && question.trim()) {
      onSubmit(question.trim());
      setQuestion("");
    }
    }
  };

  return (
    <div className="composer">
      <div className="composer-toolbar">
        <ModePicker value={mode} onChange={onModeChange} disabled={busy} />
        <label className="track-select">
          <span>轨道</span>
          <select
            value={track}
            onChange={(e) => onTrackChange(e.target.value as TrackChoice)}
            disabled={busy}
          >
            <option value="auto">自动</option>
            <option value="real">真实 LLM</option>
            <option value="scripted">离线 scripted</option>
          </select>
        </label>
      </div>
      <textarea
        className="composer-input"
        rows={3}
        placeholder="输入问题，Enter 发送，Shift+Enter 换行"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={busy}
      />
      <div className="composer-actions">
        {canStop ? (
          <button type="button" className="btn-secondary" onClick={onStop}>
            <Square size={14} /> 停止生成
          </button>
        ) : (
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !question.trim()}
            onClick={() => {
              onSubmit(question.trim());
              setQuestion("");
            }}
          >
            <SendHorizontal size={14} /> {busy ? "生成中…" : "发送"}
          </button>
        )}
      </div>
    </div>
  );
}
