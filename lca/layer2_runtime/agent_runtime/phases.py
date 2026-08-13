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

LobeHub UI → LCA gateway:
  One Run per user send (POST /runs); internal loop may multi-step.
  LiveTail projects journal as SSE (event = Journal class name).
  Browser runLcaJournal maps LlmCallStarted / ReasoningDelta / Tool* onto one assistant row.
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
