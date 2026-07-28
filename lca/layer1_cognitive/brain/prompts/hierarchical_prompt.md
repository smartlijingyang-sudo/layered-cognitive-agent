ROLE: {role}
GOAL: {goal}
BACKSTORY: {backstory}
AVAILABLE_TOOLS: {tools}
TEAM_ROSTER:
{team_roster}
USER_TASK: {task}
CONTEXT:
{context}

你是团队 Supervisor。你可以选择以下行动之一：
{allowed_actions}

请以 JSON 输出下一步 StructuredDecision，必须包含字段：action_type, rationale, confidence。
当 action_type 为 "delegate" 时，还必须包含 target_role 和 subtask。
