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
}

export interface ActivityItem {
  id: string;
  dateGroup: 'today' | 'yesterday' | 'earlier';
  icon: string;
  iconBg: string;
  title: string;
  summary: string;
  timestamp: string;
  status: 'success' | 'running' | 'warning';
  toolBadge?: string;
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
      height: 520px;
      margin: -20px -24px;
    `,
    detailSidebar: css`
      width: 250px;
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

    const selectedActivity = useMemo(
      () => activities.find((a) => a.id === selectedActivityId) || activities[0],
      [activities, selectedActivityId],
    );

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
              data.activities.map((a: any) => ({
                id: a.id,
                dateGroup: 'today',
                icon:
                  a.icon === 'mail'
                    ? '✉️'
                    : a.icon === 'terminal'
                      ? '💻'
                      : a.icon === 'browser'
                        ? '🌐'
                        : a.icon === 'robot'
                          ? '🤖'
                          : a.icon === 'clock'
                            ? '⏰'
                            : '⚙️',
                iconBg: a.status === 'running' ? '#e6f7ff' : '#f5f5f5',
                title: a.title,
                summary: a.summary,
                timestamp: a.start_time
                  ? new Date(a.start_time).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : '刚刚',
                status:
                  a.status === 'completed'
                    ? 'success'
                    : a.status === 'running'
                      ? 'running'
                      : 'warning',
                toolBadge: a.category,
                detail: {
                  toolName: a.category,
                  params: a.params,
                  result: a.result_summary,
                  durationMs: a.duration_ms,
                  runId: a.run_id,
                },
              })),
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

    // 2. 监听 WebSocket activity_updated 增量消息并原地 patch 单行
    useEffect(() => {
      const onActivityUpdated = (e: any) => {
        const patch = e.detail || e;
        if (!patch || !patch.id) return;
        setActivities((prev) => {
          const idx = prev.findIndex((item) => item.id === patch.id);
          const iconChar =
            patch.icon === 'mail'
              ? '✉️'
              : patch.icon === 'terminal'
                ? '💻'
                : patch.icon === 'browser'
                  ? '🌐'
                  : patch.icon === 'robot'
                    ? '🤖'
                    : patch.icon === 'clock'
                      ? '⏰'
                      : '⚙️';
          const statusStr =
            patch.status === 'completed'
              ? 'success'
              : patch.status === 'running'
                ? 'running'
                : 'warning';

          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = {
              ...updated[idx],
              title: patch.title || updated[idx].title,
              summary: patch.summary || updated[idx].summary,
              status: statusStr,
              detail: {
                ...updated[idx].detail,
                result: patch.resultSummary || updated[idx].detail?.result,
                durationMs: patch.durationMs ?? updated[idx].detail?.durationMs,
              },
            };
            return updated;
          }
          const newItem: ActivityItem = {
            id: patch.id,
            dateGroup: 'today',
            icon: iconChar,
            iconBg: patch.status === 'running' ? '#e6f7ff' : '#f5f5f5',
            title: patch.title || '执行操作',
            summary: patch.summary || '',
            timestamp: '刚刚',
            status: statusStr,
            toolBadge: patch.category,
            detail: {
              toolName: patch.category || patch.title,
              params: patch.params,
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
      return (
        <div
          key={act.id}
          className={styles.activityRow}
          onClick={() => {
            setSelectedActivityId(act.id);
            setDetailModalOpen(true);
          }}
        >
          <div className={styles.activityIconBox} style={{ background: act.iconBg }}>
            {act.icon}
          </div>
          <div className={styles.activityMain}>
            <div className={styles.activityTopRow}>
              <span className={styles.activityTitle}>{act.title}</span>
              <Flex align="center" gap={6}>
                {isRunning ? (
                  <>
                    <Tag color="processing" style={{ margin: 0, fontSize: 11 }}>
                      运行中
                    </Tag>
                    <Button
                      size="small"
                      danger
                      type="text"
                      style={{ fontSize: 11, height: 22, padding: '0 6px' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleStopActivity(act.id, act.detail?.runId);
                      }}
                    >
                      停止
                    </Button>
                  </>
                ) : act.status === 'success' ? (
                  <Tag color="success" style={{ margin: 0, fontSize: 11 }}>
                    ✓ 已完成
                  </Tag>
                ) : (
                  <Tag color="default" style={{ margin: 0, fontSize: 11 }}>
                    已结束
                  </Tag>
                )}
                <span style={{ fontSize: 11, color: '#8c8c8c' }}>{act.timestamp}</span>
              </Flex>
            </div>
            <div className={styles.activitySummary}>{act.summary}</div>
            <div className={styles.activityBottom}>
              {act.toolBadge && (
                <Tag color="blue" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>
                  {act.toolBadge}
                </Tag>
              )}
              {act.detail?.durationMs ? (
                <span style={{ fontSize: 11, color: '#8c8c8c' }}>耗时 {act.detail.durationMs}ms · </span>
              ) : null}
              <span>点击查看执行详情 ›</span>
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
          width={760}
          title="Agent 行动记录与人读日志"
          destroyOnClose
        >
          <div className={styles.detailModalLayout}>
            {/* 左侧列表 */}
            <div className={styles.detailSidebar}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#8c8c8c', padding: '4px 6px' }}>
                近期行动列表
              </div>
              {activities.map((act) => (
                <div
                  key={act.id}
                  className={`${styles.detailSidebarItem} ${act.id === selectedActivityId ? 'active' : ''}`}
                  onClick={() => setSelectedActivityId(act.id)}
                >
                  <Flex align="center" justify="space-between" style={{ marginBottom: 4 }}>
                    <Text strong style={{ fontSize: 12 }}>
                      {act.title}
                    </Text>
                    <span style={{ fontSize: 10, color: '#8c8c8c' }}>{act.timestamp}</span>
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
                    {act.summary}
                  </div>
                </div>
              ))}
            </div>

            {/* 右侧详情 */}
            {selectedActivity && (
              <div className={styles.detailMain}>
                <Flex align="center" justify="space-between">
                  <Title level={5} style={{ margin: 0 }}>
                    {selectedActivity.title}
                  </Title>
                  <Tag color="success">✓ 执行成功</Tag>
                </Flex>

                <div className={styles.detailSection}>
                  <span className={styles.detailSectionTitle}>📋 人读执行概述</span>
                  <Paragraph style={{ margin: 0, fontSize: 13, lineHeight: 1.6 }}>
                    {selectedActivity.detail?.humanExplanation || selectedActivity.summary}
                  </Paragraph>
                </div>

                <div className={styles.detailSection}>
                  <span className={styles.detailSectionTitle}>💻 调用工具与具体指令</span>
                  <div className={styles.codeBox}>
                    {selectedActivity.detail?.command || `${selectedActivity.detail?.toolName || 'tool'}()`}
                  </div>
                </div>

                <div className={styles.detailSection}>
                  <span className={styles.detailSectionTitle}>📊 产出与执行结果</span>
                  <div className={styles.codeBox}>
                    {selectedActivity.detail?.result || '✓ 动作已完成，状态正常'}
                  </div>
                </div>

                <Flex align="center" justify="space-between" style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    认知阶段: {selectedActivity.detail?.stage || 'Think → Act'}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    耗时: {selectedActivity.detail?.durationMs || 300}ms
                  </Text>
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
