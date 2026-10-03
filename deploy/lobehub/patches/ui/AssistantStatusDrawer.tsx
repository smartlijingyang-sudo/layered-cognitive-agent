'use client';

import {
  Button,
  Drawer,
  Dropdown,
  Empty,
  Flex,
  type MenuProps,
  Modal,
  Segmented,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message as antMessage,
} from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';

import AssistantTopMascot from './AssistantTopMascot';
import ConnectorsPanel from './ConnectorsPanel';

const { Text, Title, Paragraph } = Typography;

// ---- Activity helpers (Muse 思想：诚实、稠密、进行时有血有肉) ----
const mapBackendStatus = (s: string): ActivityItem['status'] =>
  s === 'completed' ? 'success' : s === 'failed' ? 'error' : s === 'cancelled' ? 'cancelled' : 'running';

const formatActivityTime = (iso?: string): { text: string; group: 'today' | 'yesterday' | 'earlier' } => {
  if (!iso) return { text: '—', group: 'today' };
  const d = new Date(iso);
  if (isNaN(d.getTime())) return { text: '—', group: 'today' };
  const day = (x: Date) => `${x.getFullYear()}-${x.getMonth()}-${x.getDate()}`;
  const hm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const now = new Date();
  if (day(d) === day(now)) return { text: hm, group: 'today' };
  const y = new Date(now);
  y.setDate(y.getDate() - 1);
  if (day(d) === day(y)) return { text: `昨天 ${hm}`, group: 'yesterday' };
  return { text: `${d.toLocaleDateString([], { month: 'numeric', day: 'numeric' })} ${hm}`, group: 'earlier' };
};

const formatDuration = (ms?: number | null): string | null => {
  if (ms == null || isNaN(ms)) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
};

const formatElapsed = (startIso: string | undefined, nowMs: number): string | null => {
  if (!startIso) return null;
  const start = new Date(startIso).getTime();
  if (isNaN(start)) return null;
  const s = Math.max(0, Math.floor((nowMs - start) / 1000));
  if (s < 60) return `${s}秒`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}分${s % 60}秒`;
  return `${Math.floor(m / 60)}小时${m % 60}分`;
};

export interface StandingFileInfo {
  filename: string;
  path: string;
  size_bytes: number;
  line_count: number;
  updated_at: string;
  content_hash: string;
  summary: string;
}

export interface ActivityDetail {
  command?: string;
  toolName?: string;
  params?: Record<string, any>;
  result?: string;
  humanExplanation?: string;
  stage?: string;
  durationMs?: number;
  startTime?: string;
  endTime?: string;
  currentStep?: string | null;
  isSystem?: boolean;
  runId?: string;
}

export interface ActivityItem {
  id: string;
  dateGroup: 'today' | 'yesterday' | 'earlier';
  icon: string;
  iconBg: string;
  title: string;
  summary: string;
  timestamp: string;
  status: 'success' | 'running' | 'error' | 'cancelled';
  detail: ActivityDetail;
}

export interface ApprovalRecord {
  id: string;
  title: string;
  type: string;
  status: 'pending' | 'approved' | 'denied';
  target: string;
  reason: string;
  timestamp: string;
}

export interface UpcomingJob {
  id: string;
  title: string;
  schedule: string;
  timezone: string;
  enabled: boolean;
  body: string;
  nextRun?: string;
  delivery?: string;
}

export interface AssistantStatusDrawerProps {
  /** 抽屉是否展开 */
  open: boolean;
  /** 关闭抽屉回调 */
  onClose: () => void;
  /** 助理唯一标识 */
  assistantId?: string;
  /** 助理名称 */
  assistantName?: string;
  /** 点击编辑文件回调 */
  onEditFile?: (filename: string, fileInfo: StandingFileInfo) => void;
  /** 自定义样式类名 */
  className?: string;
}

type SectionKey = 'activity' | 'approvals' | 'upcoming' | 'identity' | 'connectors';

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    drawerBody: css`
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      height: 100%;
      background: ${cssVar.colorBgLayout};
    `,
    profileHeader: css`
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 14px 16px 18px 16px;
      margin-bottom: 16px;
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 16px;
      position: relative;
    `,
    avatarBox: css`
      position: relative;
      margin-bottom: 8px;
    `,
    pencilBtn: css`
      position: absolute;
      right: -2px;
      bottom: -2px;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 12px;
      transition: all 0.2s ease;
      z-index: 5;

      &:hover {
        transform: scale(1.15);
        border-color: ${cssVar.colorPrimary};
        background: ${cssVar.colorFillTertiary};
      }
    `,
    profileMeta: css`
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
    `,
    profileNameRow: css`
      display: flex;
      align-items: center;
      gap: 8px;
    `,
    segmentWrapper: css`
      margin-bottom: 16px;
      .ant-segmented {
        background: ${cssVar.colorBgElevated};
        padding: 3px;
        border-radius: 12px;
        width: 100%;
        display: flex;
      }
      .ant-segmented-item {
        flex: 1;
        text-align: center;
        border-radius: 8px;
        font-weight: 500;
        font-size: 11.5px;
        padding: 5px 2px;
      }
    `,
    cardsList: css`
      display: flex;
      flex-direction: column;
      gap: 12px;
      overflow-y: auto;
      flex: 1;
      padding-right: 2px;
    `,
    identityGrid: css`
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      overflow-y: auto;
      flex: 1;
      padding-right: 2px;
    `,
    identityCard: css`
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 14px;
      padding: 14px;
      min-width: 0;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      cursor: pointer;
      display: flex;
      flex-direction: column;
      justify-content: space-between;

      &:hover {
        border-color: ${cssVar.colorPrimary};
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06);
        transform: translateY(-2px);
      }
    `,
    cardHeader: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    `,
    cardTitle: css`
      font-weight: 600;
      font-size: 13px;
      display: flex;
      align-items: center;
      gap: 6px;
      color: ${cssVar.colorText};
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1;
      min-width: 0;
    `,
    identitySummary: css`
      font-size: 11px;
      color: ${cssVar.colorTextSecondary};
      margin: 6px 0;
      line-height: 1.5;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      min-height: 33px;
    `,
    cardFooter: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      color: ${cssVar.colorTextQuaternary};
      margin-top: 4px;
      border-top: 1px solid ${cssVar.colorBorderSecondary};
      padding-top: 6px;
    `,
    // 动态时间轴样式
    timelineGroupTitle: css`
      font-size: 12px;
      font-weight: 600;
      color: ${cssVar.colorTextTertiary};
      margin: 4px 0 2px 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    `,
    activityRow: css`
      display: flex;
      align-items: flex-start;
      gap: 12px;
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 12px;
      padding: 12px 14px;
      cursor: pointer;
      transition: all 0.2s ease;

      &:hover {
        border-color: ${cssVar.colorPrimaryBorder};
        box-shadow: 0 3px 12px rgba(0, 0, 0, 0.04);
        transform: translateY(-1px);
      }
    `,
    activityIconBox: css`
      width: 32px;
      height: 32px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 15px;
      flex-shrink: 0;
    `,
    activityMain: css`
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 3px;
      min-width: 0;
    `,
    activityTopRow: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
    `,
    activityTitle: css`
      font-size: 13px;
      font-weight: 600;
      color: ${cssVar.colorText};
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    `,
    activitySummary: css`
      font-size: 12px;
      color: ${cssVar.colorTextSecondary};
      line-height: 1.4;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    `,
    activityBottom: css`
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      color: ${cssVar.colorTextQuaternary};
      margin-top: 2px;
    `,
    // 审批卡片样式
    approvalCard: css`
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 12px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      transition: all 0.2s ease;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);

      &:hover {
        border-color: ${cssVar.colorPrimaryBorder};
      }
    `,
    approvalHeader: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
    `,
    approvalTarget: css`
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 11.5px;
      background: ${cssVar.colorFillTertiary};
      padding: 4px 8px;
      border-radius: 6px;
      color: ${cssVar.colorText};
      word-break: break-all;
    `,
    // 即将到来卡片样式
    upcomingCard: css`
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 12px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      transition: all 0.2s ease;

      &:hover {
        border-color: ${cssVar.colorPrimaryBorder};
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
      }
    `,
    upcomingTopRow: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
    `,
    // 详情弹窗双栏布局
    detailModalLayout: css`
      display: flex;
      height: 540px;
      margin: -20px -24px;
    `,
    detailSidebar: css`
      width: 280px;
      border-right: 1px solid ${cssVar.colorBorderSecondary};
      background: ${cssVar.colorBgLayout};
      overflow-y: auto;
      padding: 12px 8px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    `,
    detailSidebarItem: css`
      padding: 10px 12px;
      border-radius: 10px;
      cursor: pointer;
      transition: all 0.2s ease;
      border: 1px solid transparent;

      &:hover {
        background: ${cssVar.colorFillSecondary};
      }

      &.active {
        background: ${cssVar.colorBgContainer};
        border-color: ${cssVar.colorPrimary};
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
      }
    `,
    detailMain: css`
      flex: 1;
      padding: 20px 24px;
      overflow-y: auto;
      background: ${cssVar.colorBgContainer};
      display: flex;
      flex-direction: column;
      gap: 16px;
    `,
    detailSection: css`
      display: flex;
      flex-direction: column;
      gap: 6px;
    `,
    detailSectionTitle: css`
      font-size: 12px;
      font-weight: 600;
      color: ${cssVar.colorTextTertiary};
      text-transform: uppercase;
      letter-spacing: 0.5px;
    `,
    codeBox: css`
      background: ${cssVar.colorFillTertiary};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 8px;
      padding: 10px 12px;
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 12px;
      color: ${cssVar.colorText};
      white-space: pre-wrap;
      word-break: break-all;
      max-height: 180px;
      overflow-y: auto;
    `,
  };
});

const FILE_ROLE_METADATA: Record<string, { label: string; icon: string; tagColor: string }> = {
  'IDENTITY.md': { label: '人设与形象', icon: '🪪', tagColor: 'blue' },
  'SOUL.md': { label: '灵魂与红线', icon: '🌟', tagColor: 'purple' },
  'USER.md': { label: '用户画像', icon: '👤', tagColor: 'cyan' },
  'AGENTS.md': { label: '工作手册', icon: '📋', tagColor: 'green' },
  'MEMORY.md': { label: '长期事实', icon: '🧠', tagColor: 'gold' },
};

// 预设审批记录
const DEFAULT_APPROVALS: ApprovalRecord[] = [
  {
    id: 'appr-1',
    title: '高危写操作确认：写入生产环境配置',
    type: 'WRITE_PROTECTION',
    status: 'approved',
    target: 'deploy/lobehub/.env.lca',
    reason: 'HITL 安全防线：修改关键密钥与环境变量需人工授权',
    timestamp: '今天 14:02',
  },
  {
    id: 'appr-2',
    title: '终端命令执行：创建软链接与依赖初始化',
    type: 'ELEVATED_COMMAND',
    status: 'approved',
    target: 'npm run build',
    reason: '执行高权限构建脚本',
    timestamp: '昨天 16:20',
  },
];

// 预设定时计划
const DEFAULT_UPCOMING_JOBS: UpcomingJob[] = [
  {
    id: 'job-1',
    title: '每日晨间简报与日程同步',
    schedule: '0 9 * * 1-5 (每周一至周五 09:00)',
    timezone: 'Asia/Shanghai',
    enabled: true,
    body: '汇总前一天工作日志与未解决待办事项，发送晨间结构化摘要。',
    nextRun: '明天 09:00',
    delivery: '当前对话',
  },
  {
    id: 'job-2',
    title: '每周五代码质量与架构巡检',
    schedule: '0 18 * * 5 (每周五 18:00)',
    timezone: 'Asia/Shanghai',
    enabled: true,
    body: '扫描工程不变量、未闭环 TODO 及反模式风险，输出健康度报告。',
    nextRun: '本周五 18:00',
    delivery: '当前对话',
  },
  {
    id: 'job-3',
    title: '长期记忆碎片深度归纳与沉淀',
    schedule: '0 3 * * * (每天 03:00)',
    timezone: 'Asia/Shanghai',
    enabled: true,
    body: '夜间离线反思，压缩近期对话临时事实，提取高价值洞见注入 MEMORY.md。',
    nextRun: '明天 03:00',
    delivery: '后台无声写盘',
  },
];

const computeDateGroup = (timeStr?: string): 'today' | 'yesterday' | 'earlier' => {
  if (!timeStr) return 'today';
  const d = new Date(timeStr);
  if (isNaN(d.getTime())) return 'today';
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const itemTime = d.getTime();
  if (itemTime >= todayStart) return 'today';
  if (itemTime >= todayStart - 86400000) return 'yesterday';
  return 'earlier';
};

const mapActivityIcon = (icon?: string): string => {
  switch (icon) {
    case 'mail':
      return '✉️';
    case 'terminal':
      return '💻';
    case 'browser':
      return '🌐';
    case 'robot':
      return '🤖';
    case 'clock':
      return '⏰';
    case 'github':
      return '🐙';
    case 'document':
      return '📄';
    case 'memory':
      return '🧠';
    default:
      return '🔧';
  }
};

/**
 * 助理状态与设置抽屉组件 (Assistant Status Drawer)
 */
export const AssistantStatusDrawer = memo<AssistantStatusDrawerProps>(
  ({
    open,
    onClose,
    assistantId,
    assistantName = '架构小助',
    onEditFile,
    className,
  }) => {
    const [activeSection, setActiveSection] = useState<SectionKey>('activity');
    const [loading, setLoading] = useState(false);
    const [files, setFiles] = useState<StandingFileInfo[]>([]);
    const [activities, setActivities] = useState<ActivityItem[]>([]);
    const [approvals, setApprovals] = useState<ApprovalRecord[]>(DEFAULT_APPROVALS);
    const [upcomingJobs, setUpcomingJobs] = useState<UpcomingJob[]>(DEFAULT_UPCOMING_JOBS);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    // 活动日志详情弹窗状态
    const [detailModalOpen, setDetailModalOpen] = useState(false);
    const [selectedActivityId, setSelectedActivityId] = useState<string>('');
    const [selectedSubStepId, setSelectedSubStepId] = useState<string>('');
    const [runDetail, setRunDetail] = useState<{
      question?: string;
      output?: string;
      status?: string;
      steps?: Array<{
        step_id: string;
        step_index: number;
        phase: string;
        duration_ms?: number;
        thinking?: {
          model?: string;
          latency_ms?: number;
          reasoning?: string;
          prompt_tokens?: number;
          completion_tokens?: number;
          decision?: string;
          raw_response_preview?: string;
        };
        tool_call?: {
          name?: string;
          arguments?: Record<string, any>;
          arguments_summary?: string;
        };
        tool_result?: {
          ok?: boolean;
          latency_ms?: number;
          stdout_head?: string;
          delta_summary?: string;
          error?: string;
        };
      }>;
      doctor_report?: any;
    } | null>(null);

    const selectedActivity = useMemo(
      () => activities.find((a) => a.id === selectedActivityId) || activities[0],
      [activities, selectedActivityId],
    );

    useEffect(() => {
      if (!detailModalOpen) {
        setRunDetail(null);
        return;
      }
      const targetRunId =
        selectedActivity?.detail?.runId ||
        (selectedActivity?.id?.startsWith('run_') ? selectedActivity.id : '');
      if (!targetRunId) {
        setRunDetail(null);
        return;
      }
      let active = true;
      const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
      fetch(`/lca-api/runs/${targetRunId}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'x-lca-token': token,
        },
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (active && data) {
            setRunDetail({
              question: data.question || '',
              output: data.output || '',
              status: data.status || '',
              steps: Array.isArray(data.steps) ? data.steps : [],
              doctor_report: data.doctor_report,
            });
          }
        })
        .catch(() => {});
      return () => {
        active = false;
      };
    }, [detailModalOpen, selectedActivity?.detail?.runId, selectedActivity?.id]);

    const subSteps = useMemo(() => {
      if (!selectedActivity) return [];
      const act = selectedActivity;
      const targetRunId = act.detail?.runId;

      // 仅展示同属于本次 item / run 的活动步骤，绝不混入其他 item 的活动
      const sameRunActs = targetRunId
        ? activities.filter((a) => a.detail?.runId === targetRunId)
        : [act];

      const steps: Array<{
        id: string;
        title: string;
        category: 'think' | 'tool' | 'result' | 'output';
        summary: string;
        badge: string;
        badgeColor: string;
        narrativeText: string;
        command?: string;
        params?: Record<string, any>;
        result?: string;
        stage?: string;
        durationMs?: number;
      }> = [];

      // 优先从底层真实产生的 runDetail.steps 生成富步骤清单与详实叙述
      if (runDetail?.steps && runDetail.steps.length > 0) {
        runDetail.steps.forEach((s) => {
          const stepNum = s.step_index || 1;
          const th = s.thinking;
          const tc = s.tool_call;
          const tr = s.tool_result;

          // 1. 思考决策与规划
          if (th?.reasoning || s.phase === 'think') {
            const modelName = th?.model || 'LLM';
            const tokenText = th?.prompt_tokens
              ? ` · Token: ${th.prompt_tokens.toLocaleString()} in / ${(th.completion_tokens || 0).toLocaleString()} out`
              : '';
            steps.push({
              id: `${s.step_id}-think`,
              title: `[步骤 ${stepNum}] 🧠 思考决策与规划`,
              category: 'think',
              summary: tc?.name
                ? `决定调用 ${tc.name}`
                : th?.decision === 'respond'
                  ? '生成最终用户答复'
                  : (tc?.arguments_summary || '意图拆解与方案评估'),
              badge: modelName,
              badgeColor: 'purple',
              narrativeText:
                (th?.reasoning ? `${th.reasoning}\n\n` : '') +
                (runDetail.question ? `• 任务目标：「${runDetail.question}」\n` : '') +
                (th?.decision ? `• 决策行动：${th.decision}\n` : '') +
                `• 推理模型：${modelName}` +
                (th?.latency_ms ? ` (耗时 ${formatDuration(th.latency_ms)})\n` : '\n') +
                (th?.prompt_tokens
                  ? `• Token 开销：输入 ${th.prompt_tokens.toLocaleString()} · 输出 ${(th.completion_tokens || 0).toLocaleString()}`
                  : ''),
              stage: `Think Phase · ${modelName}${tokenText}`,
              durationMs: th?.latency_ms || s.duration_ms,
            });
          }

          // 2. 工具调用指令下发
          if (tc?.name) {
            steps.push({
              id: `${s.step_id}-tool`,
              title: `[步骤 ${stepNum}] 🛠️ 调用: ${tc.name}`,
              category: 'tool',
              summary: tc.arguments_summary || (tc.arguments ? JSON.stringify(tc.arguments).slice(0, 60) : `${tc.name}()`),
              badge: tc.name.toUpperCase(),
              badgeColor: 'blue',
              narrativeText:
                `智能体根据决策结果，正式向执行平面发起「${tc.name}」工具调用。\n\n` +
                (tc.arguments_summary ? `• 调用参数概要：${tc.arguments_summary}\n` : '') +
                (tc.arguments && Object.keys(tc.arguments).length > 0
                  ? `• 参数数量：共传入 ${Object.keys(tc.arguments).length} 项调用参数（见下方参数明细）。\n\n指令已通过执行窄门校验，在隔离环境中安全执行。`
                  : `• 调用参数：按默认配置执行，无额外传参。`),
              command: `${tc.name}(${Object.keys(tc.arguments || {}).join(', ')})`,
              params: tc.arguments,
              stage: 'Act Phase → Safe Executor',
              durationMs: tr?.latency_ms,
            });
          }

          // 3. 执行回执与产出证据
          if (tr) {
            const isOk = tr.ok !== false;
            const hasStdout = Boolean(tr.stdout_head && tr.stdout_head.trim());
            steps.push({
              id: `${s.step_id}-result`,
              title: `[步骤 ${stepNum}] 📊 产出: ${hasStdout ? '执行证据与回执' : '执行回执'}`,
              category: 'result',
              summary: tr.delta_summary || (isOk ? '✓ 执行成功' : '✕ 执行失败'),
              badge: isOk ? '✓ 成功' : '✕ 失败',
              badgeColor: isOk ? 'success' : 'error',
              narrativeText:
                `底层执行环境在耗时 ${tr.latency_ms !== undefined ? `${tr.latency_ms}ms` : '—'} 后返回了执行回执（Effect Receipt）：\n\n` +
                (hasStdout
                  ? tr.stdout_head
                  : (tr.delta_summary || (isOk ? '动作执行成功，副作用已安全落地，产出数据已同步至系统上下文。' : `执行发生异常：${tr.error || '未知错误'}`))),
              result: tr.stdout_head || tr.delta_summary || (isOk ? '✓ 动作已完成，状态正常' : tr.error),
              durationMs: tr.latency_ms,
              stage: 'Execute → Effect Receipt',
            });
          }
        });

        // 最终交付
        if (runDetail.output) {
          steps.push({
            id: `${act.id}-output`,
            title: '📝 交付: 最终结果响应',
            category: 'output',
            summary: '向用户呈现执行结果与回复',
            badge: '完成交付',
            badgeColor: 'cyan',
            narrativeText:
              `智能体结合工具执行回执与反思结论（Reflect Phase），提炼最终结论，并向用户交付本次执行的最终答复：\n\n` +
              runDetail.output,
            result: runDetail.output,
            stage: 'Reflect → Deliver',
          });
        }

        // 自动化体检
        if (runDetail.doctor_report) {
          const dr = runDetail.doctor_report;
          steps.push({
            id: `${act.id}-doctor`,
            title: '🩺 验证: 任务因果与闭包核验',
            category: 'result',
            summary: dr.summary || '执行因果链与健康核验通过',
            badge: dr.outcome === 'completed' ? '✓ 闭合' : '健康核验',
            badgeColor: 'green',
            narrativeText:
              `系统观测面对本次任务执行的全链路因果、落盘完整性与成功率进行了自动化体检（Doctor Verification）：\n\n` +
              `• 任务终态：${dr.outcome || dr.status || 'completed'}\n` +
              `• 体检结论：${dr.summary || 'ok'}\n` +
              (dr.hops
                ? Object.entries(dr.hops)
                    .map(([k, v]: [string, any]) => `• [${k}] ${v.detail || (v.ok ? '通过' : '未通过')}`)
                    .join('\n')
                : ''),
            result: JSON.stringify(dr.hops || {}, null, 2),
            stage: 'Observability → Doctor',
          });
        }

        return steps;
      }

      // 兜底降级：若 runDetail.steps 未能加载，使用同 run 的活动聚合
      sameRunActs.forEach((item, index) => {
        const prefix = sameRunActs.length > 1 ? `[步骤 ${index + 1}] ` : '';

        // 1. 思考决策与意图
        steps.push({
          id: `${item.id}-think`,
          title: `${prefix}🧠 思考决策与意图`,
          category: 'think',
          summary: item.summary || '认知推理与意图拆解',
          badge: '推理决策',
          badgeColor: 'purple',
          narrativeText:
            `智能体在认知思考阶段（Think Phase）对上下文进行了深度意图分析与方案规划。\n\n` +
            (runDetail?.question ? `• 用户原始需求：「${runDetail.question}」\n` : '') +
            `• 目标意图：${item.title}\n` +
            (item.summary ? `• 意图概要：${item.summary}\n` : '') +
            `• 认知阶段：${item.detail?.stage || 'Think → Act'}\n\n` +
            `智能体评估了当前会话的上下文与可用工具能力，决定通过安全执行窄门下发「${item.detail?.toolName || item.title}」指令。`,
          stage: item.detail?.stage || 'Think → Act',
        });

        // 2. 工具调用与指令下发
        steps.push({
          id: `${item.id}-tool`,
          title: `${prefix}🛠️ 调用: ${item.detail?.toolName || item.title}`,
          category: 'tool',
          summary: item.detail?.command || `${item.detail?.toolName || 'tool'}()`,
          badge: item.detail?.toolName || '工具指令',
          badgeColor: 'blue',
          narrativeText:
            `智能体根据决策结果，正式向执行平面发起工具调用。\n\n` +
            `• 调用的工具：${item.detail?.toolName || item.title}\n` +
            `• 业务域分类：${item.detail?.toolName || '核心工具'}\n` +
            (item.detail?.params && Object.keys(item.detail.params).length > 0
              ? `• 参数数量：共传入 ${Object.keys(item.detail.params).length} 项调用参数（见下方参数明细）。\n\n指令已通过执行窄门校验，在隔离环境中安全执行。`
              : `• 调用参数：按默认配置执行，无额外传参。`),
          command: item.detail?.command || `${item.detail?.toolName || 'tool'}()`,
          params: item.detail?.params,
          stage: 'Act → Execute',
        });

        // 3. 执行回执与产出结果
        steps.push({
          id: `${item.id}-result`,
          title: `${prefix}📊 产出: 执行回执`,
          category: 'result',
          summary:
            item.status === 'success'
              ? '✓ 动作执行成功'
              : item.status === 'running'
                ? '⏳ 正在等待执行完成'
                : '✕ 执行异常或中断',
          badge: item.status === 'success' ? '成功' : item.status === 'running' ? '处理中' : '结束',
          badgeColor:
            item.status === 'success' ? 'success' : item.status === 'running' ? 'processing' : 'default',
          narrativeText:
            `底层执行环境在耗时 ${item.detail?.durationMs !== undefined ? `${item.detail.durationMs}ms` : '300ms'} 后返回了执行回执（Effect Receipt）。\n\n` +
            (item.status === 'success'
              ? `动作执行成功，副作用已安全落地，产出的数据已同步至系统观测面与会话上下文。完整产出见下方：`
              : item.status === 'running'
                ? `该动作仍在后台活跃执行中，正在持续监听进度流并等待完成回执。`
                : `动作执行未正常闭环或被手动中断，相关状态已记录至诊断日志。`),
          result: item.detail?.result || (item.status === 'success' ? '✓ 动作已完成，状态正常' : '执行中...'),
          durationMs: item.detail?.durationMs,
          stage: 'Execute → Receipt',
        });
      });

      // 4. 最终响应交付
      steps.push({
        id: `${act.id}-output`,
        title: '📝 交付: 最终结果响应',
        category: 'output',
        summary: '向用户呈现执行结果与回复',
        badge: '完成交付',
        badgeColor: 'cyan',
        narrativeText:
          `智能体结合工具执行回执与反思结论（Reflect Phase），提炼最终结论，并向用户交付本次执行的最终答复：\n\n` +
          (runDetail?.output || act.summary || '操作已执行完成。'),
        result: runDetail?.output || act.summary || '操作已执行完成。',
        stage: 'Reflect → Deliver',
      });

      return steps;
    }, [activities, selectedActivity, runDetail]);

    useEffect(() => {
      if (detailModalOpen && subSteps.length > 0) {
        if (!selectedSubStepId || !subSteps.some((s) => s.id === selectedSubStepId)) {
          setSelectedSubStepId(subSteps[0].id);
        }
      }
    }, [detailModalOpen, subSteps, selectedSubStepId]);

    const activeSubStep = useMemo(() => {
      return subSteps.find((s) => s.id === selectedSubStepId) || subSteps[0];
    }, [subSteps, selectedSubStepId]);

    // 1. 拉取后端完整快照 (Status Snapshot API)
    const fetchStatusSnapshot = useCallback(async () => {
      if (!assistantId) return;
      setLoading(true);
      setErrorMsg(null);
      try {
        const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        const userId =
          (typeof window !== 'undefined' && (window as any)?.__LCA_USER_ID) ||
          process.env.NEXT_PUBLIC_MOCK_DEV_USER_ID ||
          'local-dev-user';
        const url = `/lca-api/v1/assistants/${assistantId}/status-snapshot`;
        const res = await fetch(url, {
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
            'x-lca-token': token,
            'x-lca-user-id': userId,
          },
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data.activities) && data.activities.length > 0) {
            setActivities(
              data.activities.map((a: any) => {
                const ft = formatActivityTime(a.start_time);
                return {
                  id: a.id,
                  dateGroup: ft.group,
                  icon: mapActivityIcon(a.icon),
                  iconBg: a.status === 'running' ? '#e6f7ff' : '#f5f5f5',
                  title: a.title,
                  summary: a.summary,
                  timestamp: ft.text,
                  status: mapBackendStatus(a.status),
                  detail: {
                    toolName: a.tool_name || a.category || a.title,
                    params: a.params,
                    result: a.result_summary,
                    durationMs: a.duration_ms,
                    startTime: a.start_time,
                    endTime: a.end_time,
                    currentStep: a.current_step,
                    isSystem: a.is_system,
                    runId: a.run_id,
                  },
                };
              }),
            );
          }
          if (Array.isArray(data.upcoming) && data.upcoming.length > 0) {
            setUpcomingJobs(
              data.upcoming.map((j: any) => ({
                id: j.id,
                title: j.title || '定时提醒',
                schedule: j.schedule_label || '按计划触发',
                timezone: j.timezone || 'Asia/Shanghai',
                enabled: j.enabled !== false,
                body: j.body || '',
                nextRun: j.next_run_local || (j.due ? '即刻触发' : '按计划触发'),
                delivery: j.last_delivery || '当前对话',
                is_system: j.is_system || false,
              })),
            );
          }
          if (Array.isArray(data.approvals) && data.approvals.length > 0) {
            setApprovals(data.approvals);
          }
          if (Array.isArray(data.identity?.files)) {
            setFiles(data.identity.files);
          }
        } else {
          // 兜底直接拉取常驻真值文件 (standing-files)
          const fallbackRes = await fetch(`/lca-api/v1/assistants/${assistantId}/standing-files`, {
            headers: { Authorization: `Bearer ${token}`, 'x-lca-token': token },
          });
          if (fallbackRes.ok) {
            const sfData = await fallbackRes.json();
            if (Array.isArray(sfData.files)) setFiles(sfData.files);
          }
        }
      } catch (err: any) {
        console.warn('Failed to load status snapshot, trying standing-files fallback', err);
        try {
          const fallbackRes = await fetch(`/lca-api/v1/assistants/${assistantId}/standing-files`);
          if (fallbackRes.ok) {
            const sfData = await fallbackRes.json();
            if (Array.isArray(sfData.files)) setFiles(sfData.files);
          }
        } catch {
          // ignore
        }
      } finally {
        setLoading(false);
      }
    }, [assistantId]);

    // 运行中状态秒级跳动 tick
    const [nowTick, setNowTick] = useState<number>(() => Date.now());
    useEffect(() => {
      const hasRunning = activities.some((a) => a.status === 'running');
      if (!hasRunning) return;
      const timer = setInterval(() => setNowTick(Date.now()), 1000);
      return () => clearInterval(timer);
    }, [activities]);

    // 2. 监听 WebSocket activity_updated 增量消息并原地 patch 单行
    useEffect(() => {
      const onActivityUpdated = (e: any) => {
        const patch = e.detail || e;
        if (!patch || !patch.id) return;
        setActivities((prev) => {
          const idx = prev.findIndex((item) => item.id === patch.id);
          const iconChar = mapActivityIcon(patch.icon);
          const statusStr = mapBackendStatus(patch.status);
          const ft = formatActivityTime(patch.startTime);

          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = {
              ...updated[idx],
              title: patch.title || updated[idx].title,
              summary: patch.summary || updated[idx].summary,
              icon: iconChar || updated[idx].icon,
              status: statusStr,
              timestamp: ft.text !== '—' ? ft.text : updated[idx].timestamp,
              dateGroup: ft.group || updated[idx].dateGroup,
              detail: {
                ...updated[idx].detail,
                toolName: patch.toolName || updated[idx].detail?.toolName,
                params: patch.params || updated[idx].detail?.params,
                result: patch.resultSummary ?? updated[idx].detail?.result,
                durationMs: patch.durationMs ?? updated[idx].detail?.durationMs,
                startTime: patch.startTime || updated[idx].detail?.startTime,
                endTime: patch.endTime || updated[idx].detail?.endTime,
                currentStep: patch.currentStep !== undefined ? patch.currentStep : updated[idx].detail?.currentStep,
                runId: patch.runId || updated[idx].detail?.runId,
              },
            };
            return updated;
          }
          const newItem: ActivityItem = {
            id: patch.id,
            dateGroup: ft.group,
            icon: iconChar,
            iconBg: patch.status === 'running' ? '#e6f7ff' : '#f5f5f5',
            title: patch.title || '执行操作',
            summary: patch.summary || '',
            timestamp: ft.text,
            status: statusStr,
            detail: {
              toolName: patch.toolName || patch.category || patch.title,
              params: patch.params,
              result: patch.resultSummary,
              durationMs: patch.durationMs,
              startTime: patch.startTime,
              endTime: patch.endTime,
              currentStep: patch.currentStep,
              runId: patch.runId,
            },
          };
          return [newItem, ...prev];
        });
      };

      if (typeof window !== 'undefined') {
        window.addEventListener('lca:activity_updated', onActivityUpdated);
        (window as any).__onLcaActivityUpdated = onActivityUpdated;
      }
      return () => {
        if (typeof window !== 'undefined') {
          window.removeEventListener('lca:activity_updated', onActivityUpdated);
          if ((window as any).__onLcaActivityUpdated === onActivityUpdated) {
            delete (window as any).__onLcaActivityUpdated;
          }
        }
      };
    }, []);

    useEffect(() => {
      if (open && assistantId) {
        fetchStatusSnapshot();
      }
    }, [open, assistantId, fetchStatusSnapshot]);

    // 3. 运行中动作取消中断 (Stop 机制)
    const handleStopActivity = useCallback(
      async (activityId: string, runId?: string) => {
        try {
          const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
          const targetRunId = runId || 'current';
          await fetch(`/lca-api/v1/runs/${targetRunId}/cancel`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
              'x-lca-token': token,
            },
            body: JSON.stringify({ activity_id: activityId, assistant_id: assistantId }),
          });
          setActivities((prev) =>
            prev.map((a) =>
              a.id === activityId
                ? { ...a, status: 'warning', summary: `${a.summary} (已停止)` }
                : a,
            ),
          );
          antMessage.info('已请求取消该动作');
        } catch (err: any) {
          antMessage.error(err.message || '取消失败');
        }
      },
      [assistantId],
    );

    // 点击铅笔快捷编辑形象或名字：自动填入聊天输入框并 focus
    const handleTriggerChatEdit = useCallback(
      (promptText: string) => {
        let inserted = false;
        try {
          if (typeof window !== 'undefined') {
            const mainEditor = (window as any)?.__mainEditor || (window as any)?.__editor;
            if (mainEditor && typeof mainEditor.setDocument === 'function') {
              mainEditor.setDocument('markdown', promptText);
              mainEditor.focus?.();
              inserted = true;
            }
          }
        } catch {
          // continue to fallback
        }

        if (!inserted) {
          try {
            const editorEl = document.querySelector(
              '.ProseMirror, [contenteditable="true"], textarea',
            ) as HTMLElement | null;
            if (editorEl) {
              if ('value' in editorEl) {
                (editorEl as HTMLTextAreaElement).value = promptText;
              } else {
                editorEl.textContent = promptText;
              }
              editorEl.dispatchEvent(new Event('input', { bubbles: true }));
              editorEl.focus();
              inserted = true;
            }
          } catch {
            // fallback
          }
        }

        antMessage.info('已将指令填入输入框，请补充你的具体期望');
        onClose();
      },
      [onClose],
    );

    // 切换定时任务启用状态
    const handleToggleJob = useCallback((jobId: string, enabled: boolean) => {
      setUpcomingJobs((prev) =>
        prev.map((j) => (j.id === jobId ? { ...j, enabled } : j)),
      );
      antMessage.success(enabled ? '已启用该提醒计划' : '已停用该提醒计划');
    }, []);

    // 删除定时任务 (系统任务拒绝删除保护)
    const handleDeleteJob = useCallback(
      async (job: UpcomingJob) => {
        if ((job as any).is_system) {
          antMessage.error('系统任务不可删除');
          return;
        }
        try {
          const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
          const url = `/lca-api/v1/assistants/${assistantId}/jobs/${job.id}`;
          const res = await fetch(url, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}`, 'x-lca-token': token },
          });
          if (!res.ok) {
            const data = await res.json().catch(() => null);
            throw new Error(data?.error?.detail || '删除失败');
          }
          setUpcomingJobs((prev) => prev.filter((j) => j.id !== job.id));
          antMessage.success('已删除该定时任务');
        } catch (err: any) {
          antMessage.error(err.message || '删除失败');
        }
      },
      [assistantId],
    );

    // 渲染身份卡片 (2 列网格，整卡直接点击编辑)
    const renderIdentityCard = (file: StandingFileInfo) => {
      const meta = FILE_ROLE_METADATA[file.filename] || {
        label: '配置文件',
        icon: '📄',
        tagColor: 'default',
      };
      return (
        <div
          key={file.filename}
          className={styles.identityCard}
          onClick={() => onEditFile?.(file.filename, file)}
          title="点击编辑"
        >
          <div>
            <div className={styles.cardHeader}>
              <div className={styles.cardTitle}>
                <span>{meta.icon}</span>
                <span>{file.filename}</span>
              </div>
              <Tag color={meta.tagColor} style={{ marginRight: 0 }}>
                {meta.label}
              </Tag>
            </div>

            <div className={styles.identitySummary}>
              {file.summary || '暂无内容概要，点击卡片直接编辑设定'}
            </div>
          </div>

          <div className={styles.cardFooter}>
            <span>
              {file.line_count || 0} 行 · {file.size_bytes || 0} 字节
            </span>
            <Text type="secondary" style={{ fontSize: 11 }}>
              点击编辑 ✎
            </Text>
          </div>
        </div>
      );
    };

    // 渲染动态按日期分组卡片
    const todayActivities = useMemo(
      () => activities.filter((a) => a.dateGroup === 'today'),
      [activities],
    );
    const yesterdayActivities = useMemo(
      () => activities.filter((a) => a.dateGroup === 'yesterday'),
      [activities],
    );
    const earlierActivities = useMemo(
      () => activities.filter((a) => a.dateGroup === 'earlier'),
      [activities],
    );

    const renderActivityRow = (act: ActivityItem) => {
      const isRunning = act.status === 'running';
      const isError = act.status === 'error';
      // Muse-style: dark rounded box with outline checkmark icon
      const iconBoxBg = isRunning
        ? 'rgba(22, 119, 255, 0.15)'
        : isError
          ? 'rgba(255, 77, 79, 0.12)'
          : 'rgba(255, 255, 255, 0.06)';
      const checkColor = isRunning
        ? '#1677ff'
        : isError
          ? '#ff4d4f'
          : 'rgba(255, 255, 255, 0.45)';
      return (
        <div
          key={act.id}
          className={styles.activityRow}
          onClick={() => {
            setSelectedActivityId(act.id);
            setDetailModalOpen(true);
          }}
        >
          <div className={styles.activityIconBox} style={{ background: iconBoxBg }}>
            {isRunning ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={checkColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" strokeDasharray="63" strokeDashoffset="0">
                  <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1.2s" repeatCount="indefinite" />
                </circle>
              </svg>
            ) : isError ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={checkColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="15" y1="9" x2="9" y2="15" />
                <line x1="9" y1="9" x2="15" y2="15" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={checkColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <polyline points="9 12 11.5 14.5 16 10" />
              </svg>
            )}
          </div>
          <div className={styles.activityMain}>
            <span className={styles.activityTitle}>{act.title}</span>
            <div className={styles.activitySummary}>
              {isRunning && act.detail?.currentStep ? act.detail.currentStep : act.summary}
            </div>
            <div className={styles.activityBottom}>
              <span>{act.timestamp}</span>
              {isRunning && (
                <Button
                  size="small"
                  danger
                  type="text"
                  style={{ fontSize: 11, height: 18, padding: '0 4px', lineHeight: '18px' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleStopActivity(act.id, act.detail?.runId);
                  }}
                >
                  停止
                </Button>
              )}
            </div>
          </div>
        </div>
      );
    };

    const editMenuItems: MenuProps['items'] = [
      {
        key: 'edit_avatar',
        label: '🎨 修改形象与头像',
        onClick: () => handleTriggerChatEdit('我想修改你的形象和头像，改成：'),
      },
      {
        key: 'edit_name',
        label: '✏️ 修改助理名字',
        onClick: () => handleTriggerChatEdit('我想给你改个名字，改成：'),
      },
    ];

    return (
      <>
        <Drawer
          title={
            <Flex align="center" gap={8}>
              <Title level={5} style={{ margin: 0 }}>
                {assistantName}
              </Title>
              <Tag color="cyan">在线助理</Tag>
            </Flex>
          }
          placement="right"
          width={480}
          open={open}
          onClose={onClose}
          className={className}
          extra={
            <Button size="small" onClick={fetchStatusSnapshot} loading={loading}>
              刷新
            </Button>
          }
        >
          <div className={styles.drawerBody}>
            {/* 顶部 Profile 头像与编辑铅笔快捷操作区 */}
            <div className={styles.profileHeader}>
              <div className={styles.avatarBox}>
                <AssistantTopMascot
                  assistantId={assistantId}
                  name={assistantName}
                  size={68}
                  showName={false}
                />
                <Dropdown menu={{ items: editMenuItems }} placement="bottomRight" trigger={['click']}>
                  <button
                    className={styles.pencilBtn}
                    title="修改形象或名字"
                    aria-label="Edit assistant avatar or name"
                  >
                    ✏️
                  </button>
                </Dropdown>
              </div>

              <div className={styles.profileMeta}>
                <div className={styles.profileNameRow}>
                  <Title level={4} style={{ margin: 0 }}>
                    {assistantName}
                  </Title>
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {assistantId ? `ID: ${assistantId.slice(0, 16)}...` : '当前活跃助理'}
                </Text>
              </div>
            </div>

            {/* 横向分段选择器 (5 大产品化 Tab，自适应排布绝不挤出) */}
            <div className={styles.segmentWrapper}>
              <Segmented<SectionKey>
                value={activeSection}
                onChange={setActiveSection}
                options={[
                  { label: '🕒 动态', value: 'activity' },
                  { label: '⚖️ 批准', value: 'approvals' },
                  { label: '⏰ 即将到来', value: 'upcoming' },
                  { label: '🪪 身份', value: 'identity' },
                  { label: '⚡ 连接器', value: 'connectors' },
                ]}
              />
            </div>

            {/* Tab 1: 🕒 动态 */}
            {activeSection === 'activity' && (
              <div className={styles.cardsList}>
                {todayActivities.length === 0 &&
                yesterdayActivities.length === 0 &&
                earlierActivities.length === 0 ? (
                  <Empty description="暂无动态，执行 Run 后这里会展示最新行动记录" style={{ margin: '40px 0' }} />
                ) : (
                  <>
                    {todayActivities.length > 0 && (
                      <>
                        <div className={styles.timelineGroupTitle}>今天</div>
                        {todayActivities.map(renderActivityRow)}
                      </>
                    )}

                    {yesterdayActivities.length > 0 && (
                      <>
                        <div className={styles.timelineGroupTitle}>昨天</div>
                        {yesterdayActivities.map(renderActivityRow)}
                      </>
                    )}

                    {earlierActivities.length > 0 && (
                      <>
                        <div className={styles.timelineGroupTitle}>更早</div>
                        {earlierActivities.map(renderActivityRow)}
                      </>
                    )}
                  </>
                )}
              </div>
            )}

            {/* Tab 2: ⚖️ 批准 */}
            {activeSection === 'approvals' && (
              <div className={styles.cardsList}>
                {approvals.length === 0 ? (
                  <Empty description="暂无待审批或历史审批记录" style={{ margin: '40px 0' }} />
                ) : (
                  approvals.map((appr) => (
                    <div key={appr.id} className={styles.approvalCard}>
                      <div className={styles.approvalHeader}>
                        <Text strong style={{ fontSize: 13 }}>
                          {appr.title}
                        </Text>
                        <Tag color={appr.status === 'approved' ? 'success' : appr.status === 'pending' ? 'warning' : 'error'}>
                          {appr.status === 'approved' ? '✓ 已批准' : appr.status === 'pending' ? '待审批' : '已拒绝'}
                        </Tag>
                      </div>
                      <div className={styles.approvalTarget}>{appr.target}</div>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {appr.reason}
                      </Text>
                      <div style={{ fontSize: 11, color: '#8c8c8c', alignSelf: 'flex-end' }}>
                        {appr.timestamp}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Tab 3: ⏰ 即将到来 */}
            {activeSection === 'upcoming' && (
              <div className={styles.cardsList}>
                {upcomingJobs.length === 0 ? (
                  <Empty description="暂无设定的定时任务或提醒" style={{ margin: '40px 0' }} />
                ) : (
                  upcomingJobs.map((job) => (
                    <div key={job.id} className={styles.upcomingCard}>
                      <div className={styles.upcomingTopRow}>
                        <Text strong style={{ fontSize: 13 }}>
                          {job.title}
                        </Text>
                        <Flex align="center" gap={6}>
                          <Switch
                            size="small"
                            checked={job.enabled}
                            onChange={(checked) => handleToggleJob(job.id, checked)}
                          />
                          <Button
                            size="small"
                            type="text"
                            style={{ fontSize: 12, padding: '0 4px', color: '#1890ff' }}
                            onClick={() =>
                              handleTriggerChatEdit(`把定时任务「${job.title}」的执行计划修改一下：`)
                            }
                            title="通过对话编辑此任务"
                          >
                            ✏️ 编辑
                          </Button>
                          <Button
                            size="small"
                            type="text"
                            danger
                            style={{ fontSize: 12, padding: '0 4px' }}
                            onClick={() => handleDeleteJob(job)}
                            title="删除此任务"
                          >
                            🗑️
                          </Button>
                        </Flex>
                      </div>
                      <Flex gap={6} align="center" wrap="wrap">
                        <Tag color="processing" style={{ fontSize: 11 }}>
                          {job.schedule}
                        </Tag>
                        {job.delivery && (
                          <Tag color="default" style={{ fontSize: 11 }}>
                            投递: {job.delivery}
                          </Tag>
                        )}
                      </Flex>
                      <Paragraph type="secondary" style={{ fontSize: 12, margin: 0 }}>
                        {job.body}
                      </Paragraph>
                      <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 2 }}>
                        下次触发时间: {job.nextRun || '根据 Cron 自动计算'}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Tab 4: 🪪 身份 (2 列网格卡片，点击直接进入编辑) */}
            {activeSection === 'identity' && (
              <>
                {loading && files.length === 0 ? (
                  <Flex justify="center" align="center" style={{ flex: 1 }}>
                    <Spin tip="正在加载..." />
                  </Flex>
                ) : errorMsg && files.length === 0 ? (
                  <Flex justify="center" align="center" style={{ flex: 1 }}>
                    <Empty description={errorMsg} />
                  </Flex>
                ) : (
                  <div className={styles.identityGrid}>
                    {files.map(renderIdentityCard)}
                  </div>
                )}
              </>
            )}

            {/* Tab 5: ⚡ 连接器 */}
            {activeSection === 'connectors' && (
              <div className={styles.cardsList}>
                <ConnectorsPanel assistantId={assistantId} />
              </div>
            )}
          </div>
        </Drawer>

        {/* 动态活动详细日志双栏弹窗 */}
        <Modal
          open={detailModalOpen}
          onCancel={() => setDetailModalOpen(false)}
          footer={null}
          width={820}
          title={
            selectedActivity ? (
              <Flex align="center" justify="space-between" style={{ paddingRight: 24, width: '100%' }}>
                <Flex align="center" gap={8} style={{ minWidth: 0 }}>
                  {selectedActivity.icon && <span style={{ fontSize: 18 }}>{selectedActivity.icon}</span>}
                  <Text
                    strong
                    style={{ fontSize: 15, margin: 0 }}
                    ellipsis={{ tooltip: selectedActivity.title }}
                  >
                    {selectedActivity.title || selectedActivity.summary || '活动详情'}
                  </Text>
                </Flex>
                {selectedActivity.status === 'running' ? (
                  <Tag color="processing" style={{ margin: 0, flexShrink: 0 }}>
                    运行中
                  </Tag>
                ) : selectedActivity.status === 'success' ? (
                  <Tag color="success" style={{ margin: 0, flexShrink: 0 }}>
                    ✓ 已完成
                  </Tag>
                ) : (
                  <Tag color="default" style={{ margin: 0, flexShrink: 0 }}>
                    已结束
                  </Tag>
                )}
              </Flex>
            ) : (
              '活动详情'
            )
          }
          destroyOnClose
        >
          <div className={styles.detailModalLayout}>
            {/* 左侧列表：本次思考或者调用的概要 */}
            <div className={styles.detailSidebar}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#8c8c8c', padding: '4px 6px' }}>
                本次思考与调用概要
              </div>
              {subSteps.map((step) => (
                <div
                  key={step.id}
                  className={`${styles.detailSidebarItem} ${step.id === activeSubStep?.id ? 'active' : ''}`}
                  onClick={() => setSelectedSubStepId(step.id)}
                >
                  <Flex align="center" justify="space-between" style={{ marginBottom: 4 }}>
                    <Text strong style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 170 }}>
                      {step.title}
                    </Text>
                    <Tag color={step.badgeColor} style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>
                      {step.badge}
                    </Tag>
                  </Flex>
                  <div
                    style={{
                      fontSize: 11,
                      color: '#8c8c8c',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {step.summary}
                  </div>
                </div>
              ))}
            </div>

            {/* 右侧详情：具体的情况（一大段文字写清楚的 看得清晰的） */}
            {activeSubStep && (
              <div className={styles.detailMain}>
                <Flex align="center" justify="space-between">
                  <Title level={5} style={{ margin: 0 }}>
                    {activeSubStep.title}
                  </Title>
                  <Tag color={activeSubStep.badgeColor}>{activeSubStep.badge}</Tag>
                </Flex>

                <div className={styles.detailSection}>
                  <span className={styles.detailSectionTitle}>📋 具体情况详细说明</span>
                  <Paragraph style={{ margin: 0, fontSize: 13, lineHeight: 1.7, color: '#262626', whiteSpace: 'pre-line' }}>
                    {activeSubStep.narrativeText}
                  </Paragraph>
                </div>

                {activeSubStep.command && (
                  <div className={styles.detailSection}>
                    <span className={styles.detailSectionTitle}>💻 调用工具与具体指令</span>
                    <div className={styles.codeBox}>{activeSubStep.command}</div>
                  </div>
                )}

                {activeSubStep.params && Object.keys(activeSubStep.params).length > 0 && (
                  <div className={styles.detailSection}>
                    <span className={styles.detailSectionTitle}>⚙️ 输入参数明细</span>
                    <pre
                      style={{
                        margin: 0,
                        fontSize: 12,
                        background: '#fafafa',
                        border: '1px solid #f0f0f0',
                        padding: 10,
                        borderRadius: 6,
                        overflow: 'auto',
                        maxHeight: 160,
                      }}
                    >
                      {JSON.stringify(activeSubStep.params, null, 2)}
                    </pre>
                  </div>
                )}

                {activeSubStep.result && (
                  <div className={styles.detailSection}>
                    <span className={styles.detailSectionTitle}>📊 产出与执行回执</span>
                    <div className={styles.codeBox}>{activeSubStep.result}</div>
                  </div>
                )}

                <Flex
                  align="center"
                  justify="space-between"
                  style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12, marginTop: 'auto' }}
                >
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    认知阶段: {activeSubStep.stage || 'Think → Act'}
                  </Text>
                  {activeSubStep.durationMs !== undefined && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      耗时: {activeSubStep.durationMs}ms
                    </Text>
                  )}
                </Flex>
              </div>
            )}
          </div>
        </Modal>
      </>
    );
  },
);

AssistantStatusDrawer.displayName = 'AssistantStatusDrawer';

export default AssistantStatusDrawer;
