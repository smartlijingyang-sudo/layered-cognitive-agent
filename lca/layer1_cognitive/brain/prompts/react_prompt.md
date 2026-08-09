ROLE: {role}
GOAL: {goal}
BACKSTORY: {backstory}
AVAILABLE_TOOLS: {tools}
USER_TASK: {task}
CONTEXT:
{context}

你可以选择以下行动之一：
{allowed_actions}

请以 JSON 输出下一步 Decision（字段：action_type / rationale / confidence；
use_tool 时附 tool_name+arguments；respond 时附顶层 response_text）。
严禁把 respond 写成 use_tool 或 tool_name:"respond"——回复用户只能用 action_type:"respond"。
