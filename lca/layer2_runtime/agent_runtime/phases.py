"""LobeHub AgentRuntime phase ↔ LCA layer mapping.

LobeHub (TypeScript)              LCA (Python)
─────────────────────────────────────────────────────────────
AgentRuntime.step loop            CognitiveRuntime._loop
  user_input / call_llm phase       Reasoner.generate_thoughts
                                    └─ llm_turn.execute_llm_turn  (call_llm)
  llm_result phase                  ModularBrain.think
                                    └─ llm_result.build_decision_from_response
  call_tool / call_tools_batch      Body.act (SafeExecutor)
  finish                            DefaultStopOutcomePolicy (RESPOND → stop)

G2A Mode A (LobeHub UI → LCA gateway):
  One outward OpenAI SSE per user send; internal loop may multi-step.
  JournalOpenAiProjector maps journal → delta.content / tool_calls / lca.events.
  finish_reason must always be ``stop`` (never ``tool_calls``).
"""

from __future__ import annotations

from enum import Enum


class AgentPhase(str, Enum):
    """Stable phase ids aligned with @lobechat/agent-runtime context.phase."""

    USER_INPUT = "user_input"
    CALL_LLM = "call_llm"
    LLM_RESULT = "llm_result"
    TOOL_RESULT = "tool_result"
    TOOLS_BATCH_RESULT = "tools_batch_result"
    FINISH = "finish"


#: LobeHub GeneralChatAgent: no tool_calls → finish (not retry with tool_choice).
LOBEHUB_TEXT_ONLY_MEANS_FINISH = True

#: G2A outward SSE must not signal OpenAI tool-loop continuation.
G2A_FINISH_REASON = "stop"
