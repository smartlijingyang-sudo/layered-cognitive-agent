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

export interface ModalStepItem {
  id: string;
  step_title: string;
  iconType: 'started' | 'completed' | 'pending' | 'running' | 'error';
  narrative: string;
  command?: string;
  exit_code?: number;
  duration_ms?: number;
  truncated_boundary?: string;
  code_snippets?: Array<{ label: string; code: string; language?: string }>;
  search_results?: Array<{ index: number; location: string; match: string }>;
  conclusion?: string;
  stage?: string;
  params?: Record<string, any>;
  result?: string;
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
    codeBlockWrapper: css`
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 8px;
      overflow: hidden;
      background: ${cssVar.colorFillTertiary};
    `,
    codeBlockHeader: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 4px 10px;
      background: ${cssVar.colorFillSecondary};
      border-bottom: 1px solid ${cssVar.colorBorderSecondary};
    `,
    codeBlockLang: css`
      font-size: 11px;
      font-weight: 600;
      color: ${cssVar.colorTextTertiary};
      font-family: ui-monospace, SFMono-Regular, monospace;
      text-transform: lowercase;
    `,
    metadataBullets: css`
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 12px;
      color: ${cssVar.colorTextSecondary};
      font-family: ui-monospace, SFMono-Regular, monospace;
      background: ${cssVar.colorFillQuaternary};
      padding: 8px 12px;
      border-radius: 6px;
    `,
    searchResultsList: css`
      display: flex;
      flex-direction: column;
      gap: 8px;
    `,
    searchResultItem: css`
      display: flex;
      flex-direction: column;
      gap: 2px;
    `,
    searchResultIndex: css`
      font-size: 12px;
      font-weight: 700;
      color: ${cssVar.colorText};
      width: 18px;
    `,
    searchResultLoc: css`
      font-size: 12px;
      font-weight: 600;
      color: ${cssVar.colorPrimary};
      font-family: ui-monospace, SFMono-Regular, monospace;
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
        evidence?: any;
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

    const subSteps = useMemo<ModalStepItem[]>(() => {
      if (!selectedActivity) return [];
      const act = selectedActivity;
      const targetRunId = act.detail?.runId;

      const steps: ModalStepItem[] = [];

      // 1. 首节点：● 已开始 (gray bullet, no icon)
      const taskGoal = runDetail?.question || act.title || '验证Activity重启与事件完整性';
      steps.push({
        id: `${act.id}-started`,
        step_title: '已开始',
        iconType: 'started',
        narrative: `智能体接收到任务目标：「${taskGoal}」。\n\n已成功初始化运行环境、挂载会话上下文与执行能力契约。`,
        conclusion: '验证结论：任务初始化完成，已开始执行认知决策与行动规划。',
        stage: 'Lifecycle → Started',
      });

      // 2. 后续节点：真实动作步骤（动态自然语言，绝不机械分割为思考/调用/回执）
      if (runDetail?.steps && runDetail.steps.length > 0) {
        runDetail.steps.forEach((s) => {
          const tc = s.tool_call;
          const tr = s.tool_result;
          const th = s.thinking;
          const ev = (s as any).evidence;

          if (ev) {
            steps.push({
              id: s.step_id || `step-${s.step_index}`,
              step_title: ev.step_title || tc?.name || '执行操作',
              iconType: ev.exit_code === 0 ? 'completed' : 'error',
              narrative: ev.narrative || th?.reasoning || '执行动作指令',
              command: ev.command,
              exit_code: ev.exit_code,
              duration_ms: ev.duration_ms,
              truncated_boundary: ev.truncated_boundary,
              code_snippets: ev.code_snippets,
              search_results: ev.search_results,
              conclusion: ev.conclusion || '验证结论：动作执行完成，符合预期，无执行错误。',
              stage: s.phase || 'Act Phase',
            });
          } else if (tc?.name) {
            const isOk = tr?.ok !== false;
            const dur = tr?.latency_ms || s.duration_ms || 0;
            const cmdStr = `${tc.name}(${Object.keys(tc.arguments || {}).join(', ')})`;
            steps.push({
              id: s.step_id || `step-${s.step_index}`,
              step_title: tc.arguments_summary || tc.name,
              iconType: isOk ? 'completed' : 'error',
              narrative: th?.reasoning ? `${th.reasoning}\n\n执行工具调用：${tc.name}` : `执行工具调用：${tc.name}`,
              command: cmdStr,
              exit_code: isOk ? 0 : 1,
              duration_ms: dur,
              code_snippets: tr?.stdout_head
                ? [{ label: '提取到的代码内容', code: tr.stdout_head, language: 'bash' }]
                : undefined,
              conclusion: isOk
                ? '验证结论：动作执行完成，符合预期，无执行错误。'
                : `执行异常：动作未达预期，错误信息：${tr?.error || '未知错误'}`,
              stage: s.phase || 'Act Phase',
              params: tc.arguments,
              result: tr?.stdout_head || tr?.delta_summary,
            });
          }
        });

        // 最终交付
        if (runDetail.output) {
          steps.push({
            id: `${act.id}-output`,
            step_title: '交付任务结果与答复',
            iconType: 'completed',
            narrative: runDetail.output,
            conclusion: '验证结论：智能体已完成本轮执行并生成最终用户响应。',
            stage: 'Reflect → Deliver',
          });
        }
      } else {
        // 降级回退：使用 sameRunActs
        const sameRunActs = targetRunId
          ? activities.filter((a) => a.detail?.runId === targetRunId)
          : [act];
        sameRunActs.forEach((item) => {
          steps.push({
            id: item.id,
            step_title: item.title,
            iconType: item.status === 'success' ? 'completed' : item.status === 'running' ? 'pending' : 'error',
            narrative: item.summary || item.detail?.humanExplanation || `执行操作：${item.title}`,
            command: item.detail?.command || (item.detail?.toolName ? `${item.detail.toolName}()` : undefined),
            exit_code: item.status === 'error' ? 1 : 0,
            duration_ms: item.detail?.durationMs || 300,
            truncated_boundary: item.detail?.result?.includes('ZZSTART') ? 'ZZSTART / ZZEND' : undefined,
            code_snippets: item.detail?.result
              ? [{ label: '提取到的代码内容', code: item.detail.result, language: 'bash' }]
              : undefined,
            conclusion: item.status === 'success'
              ? `验证结论：${item.title} 已顺利完成，系统状态一致。`
              : '执行中或已中断。',
            params: item.detail?.params,
            result: item.detail?.result,
          });
        });
      }

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
          width={840}
          title={
            selectedActivity ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingRight: 32 }}>
                <div>
                  {selectedActivity.status === 'running' ? (
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '2px 10px',
                        borderRadius: 12,
                        background: 'rgba(22, 119, 255, 0.1)',
                        color: '#1677ff',
                        fontSize: 12,
                        fontWeight: 600,
                      }}
                    >
                      进行中
                    </span>
                  ) : selectedActivity.status === 'error' ? (
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '2px 10px',
                        borderRadius: 12,
                        background: 'rgba(255, 77, 79, 0.1)',
                        color: '#ff4d4f',
                        fontSize: 12,
                        fontWeight: 600,
                      }}
                    >
                      执行失败
                    </span>
                  ) : (
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '2px 10px',
                        borderRadius: 12,
                        background: '#e6f7ec',
                        color: '#1a7f37',
                        fontSize: 12,
                        fontWeight: 600,
                      }}
                    >
                      已完成
                    </span>
                  )}
                </div>
                <Title level={4} style={{ margin: 0, fontWeight: 700, fontSize: 16 }}>
                  {selectedActivity.title || selectedActivity.summary || '活动详情'}
                </Title>
              </div>
            ) : (
              <Title level={4} style={{ margin: 0, fontWeight: 700, fontSize: 16 }}>
                活动详情
              </Title>
            )
          }
          destroyOnClose
        >
          <div className={styles.detailModalLayout}>
            {/* 左侧列表：Muse 风格步骤树 */}
            <div className={styles.detailSidebar}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#8c8c8c', padding: '4px 6px' }}>
                本次思考与调用概要
              </div>
              {subSteps.map((step) => {
                const isSelected = step.id === activeSubStep?.id;
                return (
                  <div
                    key={step.id}
                    className={`${styles.detailSidebarItem} ${isSelected ? 'active' : ''}`}
                    onClick={() => setSelectedSubStepId(step.id)}
                  >
                    <Flex align="center" gap={8}>
                      {step.iconType === 'started' ? (
                        <span style={{ color: '#8c8c8c', fontSize: 13, flexShrink: 0 }}>●</span>
                      ) : step.iconType === 'completed' ? (
                        <span style={{ color: '#52c41a', fontSize: 13, fontWeight: 'bold', flexShrink: 0 }}>✓</span>
                      ) : step.iconType === 'pending' || step.iconType === 'running' ? (
                        <span style={{ color: '#8c8c8c', fontSize: 13, flexShrink: 0 }}>☐</span>
                      ) : (
                        <span style={{ color: '#ff4d4f', fontSize: 13, fontWeight: 'bold', flexShrink: 0 }}>✕</span>
                      )}
                      <Text
                        strong={isSelected}
                        style={{
                          fontSize: 12.5,
                          color: isSelected ? '#1677ff' : '#262626',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          flex: 1,
                        }}
                      >
                        {step.step_title}
                      </Text>
                    </Flex>
                  </div>
                );
              })}
            </div>

            {/* 右侧详情：高保真 5 要素证据面板 */}
            {activeSubStep && (
              <div className={styles.detailMain}>
                {/* 1. 粗体步骤大标题 */}
                <Title level={4} style={{ margin: 0, fontWeight: 700, fontSize: 16 }}>
                  {activeSubStep.step_title}
                </Title>

                {/* 2. 叙述段落 */}
                <div className={styles.detailSection}>
                  <span className={styles.detailSectionTitle}>📋 具体情况详细说明</span>
                  <Paragraph style={{ margin: 0, fontSize: 13, lineHeight: 1.7, color: '#262626', whiteSpace: 'pre-line' }}>
                    {activeSubStep.narrative}
                  </Paragraph>
                </div>

                {/* 3. 执行的命令:: 代码块 */}
                {activeSubStep.command && (
                  <div className={styles.detailSection}>
                    <span className={styles.detailSectionTitle}>执行的命令::</span>
                    <div className={styles.codeBlockWrapper}>
                      <div className={styles.codeBlockHeader}>
                        <span className={styles.codeBlockLang}>bash</span>
                        <Button
                          type="text"
                          size="small"
                          style={{ fontSize: 11, color: '#8c8c8c', height: 22, padding: '0 6px' }}
                          onClick={() => {
                            if (typeof navigator !== 'undefined' && navigator.clipboard) {
                              navigator.clipboard.writeText(activeSubStep.command || '');
                              antMessage.success('已复制命令');
                            }
                          }}
                        >
                          复制
                        </Button>
                      </div>
                      <div className={styles.codeBox}>{activeSubStep.command}</div>
                    </div>
                  </div>
                )}

                {/* 4. 元数据信息点 (退出码、耗时、边界截取) */}
                {(activeSubStep.exit_code !== undefined || activeSubStep.duration_ms !== undefined) && (
                  <div className={styles.metadataBullets}>
                    <div>
                      · 退出码: {activeSubStep.exit_code ?? 0}, 耗时: {activeSubStep.duration_ms ?? 0}ms
                    </div>
                    {activeSubStep.truncated_boundary && (
                      <div>· 输出已通过 {activeSubStep.truncated_boundary} 边界截取</div>
                    )}
                  </div>
                )}

                {/* 5. 提取到的代码内容 / 检索结果 */}
                {activeSubStep.search_results && activeSubStep.search_results.length > 0 ? (
                  <div className={styles.detailSection}>
                    <span className={styles.detailSectionTitle}>检索结果：</span>
                    <div className={styles.searchResultsList}>
                      {activeSubStep.search_results.map((res, i) => (
                        <div key={i} className={styles.searchResultItem}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span className={styles.searchResultIndex}>{res.index || i + 1}.</span>
                            <span className={styles.searchResultLoc}>{res.location}</span>
                          </div>
                          <div className={styles.codeBox} style={{ margin: '4px 0 0', maxHeight: 80 }}>
                            {res.match}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : activeSubStep.code_snippets && activeSubStep.code_snippets.length > 0 ? (
                  <div className={styles.detailSection}>
                    {activeSubStep.code_snippets.map((snip, i) => (
                      <div key={i} style={{ marginBottom: 10 }}>
                        <span className={styles.detailSectionTitle}>{snip.label || '提取到的代码内容'}</span>
                        <div className={styles.codeBlockWrapper}>
                          <div className={styles.codeBlockHeader}>
                            <span className={styles.codeBlockLang}>{snip.language || 'bash'}</span>
                            <Button
                              type="text"
                              size="small"
                              style={{ fontSize: 11, color: '#8c8c8c', height: 22, padding: '0 6px' }}
                              onClick={() => {
                                if (typeof navigator !== 'undefined' && navigator.clipboard) {
                                  navigator.clipboard.writeText(snip.code || '');
                                  antMessage.success('已复制代码内容');
                                }
                              }}
                            >
                              复制
                            </Button>
                          </div>
                          <div className={styles.codeBox}>{snip.code}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : activeSubStep.result ? (
                  <div className={styles.detailSection}>
                    <span className={styles.detailSectionTitle}>提取到的代码内容</span>
                    <div className={styles.codeBox}>{activeSubStep.result}</div>
                  </div>
                ) : null}

                {/* 输入参数明细 (若有) */}
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
                        maxHeight: 140,
                      }}
                    >
                      {JSON.stringify(activeSubStep.params, null, 2)}
                    </pre>
                  </div>
                )}

                {/* 6. 验证结论 */}
                {activeSubStep.conclusion && (
                  <div className={styles.detailSection}>
                    <span className={styles.detailSectionTitle} style={{ fontWeight: 700, color: '#262626', fontSize: 13 }}>
                      验证结论
                    </span>
                    <Paragraph style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: '#262626', whiteSpace: 'pre-line' }}>
                      {activeSubStep.conclusion}
                    </Paragraph>
                  </div>
                )}

                <Flex
                  align="center"
                  justify="space-between"
                  style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12, marginTop: 'auto' }}
                >
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    认知阶段: {activeSubStep.stage || 'Act Phase'}
                  </Text>
                  {activeSubStep.duration_ms !== undefined && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      耗时: {activeSubStep.duration_ms}ms
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
