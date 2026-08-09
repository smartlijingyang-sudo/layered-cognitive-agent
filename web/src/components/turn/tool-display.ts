/**
 * LobeHub-style tool display names, workflow summary, and arg headlines.
 */

import type { ToolBlock, TurnProcessBlock } from "../../projectors/types";
import { formatProcessDuration } from "../../lib/format-duration";
import {
  TOOL_FIRST_DETAIL_MAX_CHARS,
  TOOL_HEADLINE_DETAIL_MAX_CHARS,
  TOOL_HEADLINE_TRUNCATION_SUFFIX,
  WORKFLOW_SUMMARY_TOP_N,
} from "./workflow-constants";

/** Verb-style Chinese labels (workflow summary + tool title). */
export const TOOL_DISPLAY_NAMES: Record<string, string> = {
  // Sandbox / code
  run_code: "执行了代码",
  run_sandbox_code: "执行了代码",
  sandbox_execute: "运行了命令",
  sandbox_inspect: "探查了沙箱",
  calculator: "完成了计算",
  write_file: "写入了文件",
  export_file: "导出了文件",
  read_file: "读取了文件",
  get_weather: "查询了天气",
  // Skills (ADR-0048)
  search_skill: "搜索了技能",
  import_skill: "导入了技能",
  activate_skill: "启用了技能",
  read_skill_reference: "读取了技能资源",
  run_skill_script: "执行了技能脚本",
  // Generic / legacy
  activate_tools: "启用了工具",
  run_command: "运行了命令",
  execute_code: "执行了代码",
};

/** Short API-style labels for tool row (Inspector). */
export const TOOL_API_LABELS: Record<string, string> = {
  run_code: "执行代码",
  run_sandbox_code: "沙箱执行",
  sandbox_execute: "执行命令",
  sandbox_inspect: "沙箱探查",
  calculator: "计算器",
  write_file: "写入文件",
  export_file: "导出文件",
  read_file: "读取文件",
  get_weather: "天气",
  search_skill: "搜索技能",
  import_skill: "导入技能",
  activate_skill: "启用技能",
  read_skill_reference: "读取技能资源",
  run_skill_script: "执行技能脚本",
  activate_tools: "启用工具",
  run_command: "执行命令",
};

function toTitleCase(apiName: string): string {
  return apiName
    .replaceAll(/[_-]+/g, " ")
    .replaceAll(/([A-Z])/g, " $1")
    .replace(/^./, (s) => s.toUpperCase())
    .trim();
}

export function getToolDisplayName(toolName: string): string {
  return TOOL_DISPLAY_NAMES[toolName] ?? toTitleCase(toolName);
}

export function getToolApiLabel(toolName: string): string {
  return TOOL_API_LABELS[toolName] ?? toTitleCase(toolName);
}

export function truncateDetail(
  value: string,
  max = TOOL_FIRST_DETAIL_MAX_CHARS,
): string {
  const s = value.trim();
  if (s.length <= max) return s;
  return s.slice(0, max) + TOOL_HEADLINE_TRUNCATION_SUFFIX;
}

/** Parse tool arguments preview (JSON or raw string). */
export function parseToolArgs(raw: string | undefined): Record<string, unknown> {
  if (!raw?.trim()) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // not JSON
  }
  return { value: raw };
}

/** Prefer human-readable summary for collapsed titles (not raw command/code). */
const HUMAN_SUMMARY_KEYS = [
  "description",
  "summary",
  "title",
  "task",
  "intent",
  "purpose",
  "message",
  "step_message",
  "stepMessage",
] as const;

/** Keys for executable payload in expand body. */
const COMMAND_KEYS = ["command", "cmd", "shell"] as const;
const CODE_KEYS = ["code", "expression", "source"] as const;

export function getToolHumanSummary(args: Record<string, unknown>): string {
  for (const key of HUMAN_SUMMARY_KEYS) {
    const val = args[key];
    if (typeof val === "string" && val.trim()) {
      return truncateDetail(val, TOOL_FIRST_DETAIL_MAX_CHARS);
    }
  }
  return "";
}

export function getToolFirstDetail(tool: ToolBlock): string {
  const args = parseToolArgs(tool.argumentsPreview);
  const human = getToolHumanSummary(args);
  if (human) return human;

  for (const key of [...COMMAND_KEYS, ...CODE_KEYS, "skill_id", "name", "query", "path", "filename", "file_name"] as const) {
    const val = args[key];
    if (typeof val === "string" && val.trim()) {
      return truncateDetail(val, TOOL_FIRST_DETAIL_MAX_CHARS);
    }
  }
  for (const val of Object.values(args)) {
    if (typeof val === "string" && val.trim()) {
      return truncateDetail(val, TOOL_FIRST_DETAIL_MAX_CHARS);
    }
  }
  return "";
}

export function getToolHeadlineLine(tool: ToolBlock): string {
  const label = getToolDisplayName(tool.toolName);
  const args = parseToolArgs(tool.argumentsPreview);
  const human = getToolHumanSummary(args);
  const detail = human || getToolFirstDetail(tool);
  if (!detail) return label;
  const short =
    detail.length > TOOL_HEADLINE_DETAIL_MAX_CHARS
      ? detail.slice(0, TOOL_HEADLINE_DETAIL_MAX_CHARS - 1) + TOOL_HEADLINE_TRUNCATION_SUFFIX
      : detail;
  return human ? short : `${label}: ${short}`;
}

export type WorkflowCompletionStatus = "success" | "partial" | "error";

export function getWorkflowCompletionStatus(
  tools: readonly ToolBlock[],
): WorkflowCompletionStatus {
  if (tools.length === 0) return "success";
  const finished = tools.filter((t) => t.status === "done" || t.status === "error");
  if (finished.length === 0) return "success";
  const errors = finished.filter((t) => t.status === "error" || t.ok === false).length;
  if (errors === 0) return "success";
  if (errors === finished.length) return "error";
  return "partial";
}

export function areWorkflowToolsComplete(tools: readonly ToolBlock[]): boolean {
  if (tools.length === 0) return false;
  return tools.every((t) => t.status === "done" || t.status === "error");
}

/**
 * Completed workflow title, e.g.
 * "15 次调用：启用了工具, 搜索了技能, 运行了命令 · 思考了 12s"
 */
export function getWorkflowSummaryText(
  tools: readonly ToolBlock[],
  thinkingDurationMs?: number,
): string {
  if (tools.length === 0) return "处理完成";

  const groups = new Map<string, { count: number; errorCount: number }>();
  for (const tool of tools) {
    const existing = groups.get(tool.toolName) ?? { count: 0, errorCount: 0 };
    existing.count += 1;
    if (tool.status === "error" || tool.ok === false) existing.errorCount += 1;
    groups.set(tool.toolName, existing);
  }

  const entries = [...groups.entries()];
  const totalKinds = entries.length;
  const totalCalls = entries.reduce((sum, [, { count }]) => sum + count, 0);
  const totalErrors = entries.reduce((sum, [, { errorCount }]) => sum + errorCount, 0);

  const formatPart = ([name, info]: [string, { count: number }]): string => {
    const label = getToolDisplayName(name);
    return info.count > 1 ? `${label} (${info.count})` : label;
  };

  const displayed =
    totalKinds <= WORKFLOW_SUMMARY_TOP_N + 1
      ? entries
      : [...entries].sort(([, a], [, b]) => b.count - a.count).slice(0, WORKFLOW_SUMMARY_TOP_N);

  let toolsText = displayed.map(formatPart).join(", ");
  if (displayed.length < totalKinds) {
    toolsText += ` 等 ${totalKinds} 种工具`;
  }

  const segments: string[] =
    totalKinds > 1 && totalCalls > totalKinds
      ? [`${totalCalls} 次调用：${toolsText}`]
      : [toolsText];

  if (totalErrors > 0) {
    segments.push(`${totalErrors} 次失败`);
  }

  let result = segments.join(" · ");
  if (thinkingDurationMs != null && thinkingDurationMs > 0) {
    const d = formatProcessDuration(thinkingDurationMs);
    if (d) result += ` · 思考了 ${d}`;
  }
  return result;
}

export function collectToolsFromProcess(
  blocks: readonly TurnProcessBlock[],
): ToolBlock[] {
  return blocks.filter((b): b is ToolBlock => b.kind === "tool");
}

export function extractCommand(args: Record<string, unknown>): string {
  for (const key of COMMAND_KEYS) {
    const v = args[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  return "";
}

export function extractCode(args: Record<string, unknown>): string {
  for (const key of CODE_KEYS) {
    const v = args[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  return "";
}

export function extractSkillId(args: Record<string, unknown>): string {
  for (const key of ["skill_id", "name", "identifier", "query"] as const) {
    const v = args[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  return "";
}

export function isCommandLikeTool(toolName: string): boolean {
  return toolName === "run_skill_script" || toolName === "run_command";
}

export function isCodeLikeTool(toolName: string): boolean {
  return (
    toolName === "run_code" ||
    toolName === "run_sandbox_code" ||
    toolName === "sandbox_execute" ||
    toolName === "calculator"
  );
}

export function isSkillLikeTool(toolName: string): boolean {
  return (
    toolName === "search_skill" ||
    toolName === "import_skill" ||
    toolName === "activate_skill" ||
    toolName === "read_skill_reference"
  );
}
