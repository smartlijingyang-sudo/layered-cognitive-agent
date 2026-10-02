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
      grid-template-columns: repeat(2, 1fr);
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

// 预设高拟真人读行动日志
const DEFAULT_ACTIVITIES: ActivityItem[] = [
  {
    id: 'act-1',
    dateGroup: 'today',
    icon: '✓',
    iconBg: 'rgba(82, 196, 26, 0.12)',
    title: '检索并更新记忆偏好',
    summary: '自动识别用户架构偏好（DDD思维与TypeScript规范），并成功同步至长期事实。',
    timestamp: '15:24',
    status: 'success',
    toolBadge: 'memory',
    detail: {
      stage: 'Reflect → Remember',
      toolName: 'memory_update',
      humanExplanation: '助理在与你的交谈中捕获了架构工程规范，判定为长期偏好事实，执行了幂等写盘。',
      command: 'memory_update(scope="architecture_principles", key="ddd_guardrails")',
      result: '✓ 事实已写入 MEMORY.md，索引哈希: e4f82a90...',
      durationMs: 320,
    },
  },
  {
    id: 'act-2',
    dateGroup: 'today',
    icon: '💻',
    iconBg: 'rgba(22, 119, 255, 0.12)',
    title: '执行系统健康与环境探测',
    summary: '运行了机器环境诊断命令，核验本地 Companion 连接链路及 Python 运行环境。',
    timestamp: '14:10',
    status: 'success',
    toolBadge: 'shell',
    detail: {
      stage: 'Perceive → Act',
      toolName: 'local_runCommand',
      humanExplanation: '执行轻量级探测命令以确认执行环境状态，确保后续文件修改与工具执行可用。',
      command: 'python3 --version && uname -a',
      result: 'Python 3.12.3\nLinux 6.8.0-45-generic x86_64 GNU/Linux',
      durationMs: 450,
    },
  },
  {
    id: 'act-3',
    dateGroup: 'today',
    icon: '🌐',
    iconBg: 'rgba(19, 194, 194, 0.12)',
    title: '检索外部生态服务状态',
    summary: '同步 Google Drive 与 Gmail 授权状态，连接健康无漂移。',
    timestamp: '11:45',
    status: 'success',
    toolBadge: 'connectors',
    detail: {
      stage: 'Think → Observe',
      toolName: 'composio_verify_status',
      humanExplanation: '后台轮询生态连接凭证有效期，确认 Gmail 与 GitHub 连接器持续活跃。',
      command: 'GET /lca-api/composio/connections',
      result: '{"active_apps": ["gmail", "github"], "status": "READY"}',
      durationMs: 210,
    },
  },
  {
    id: 'act-4',
    dateGroup: 'yesterday',
    icon: '📄',
    iconBg: 'rgba(114, 46, 209, 0.12)',
    title: '更新工作手册 AGENTS.md 准则',
    summary: '根据系统架构演进，新增了 UI 补丁防裁剪与连接器安全约束。',
    timestamp: '昨天 17:30',
    status: 'success',
    toolBadge: 'file_edit',
    detail: {
      stage: 'Act → Commit',
      toolName: 'replace_file_content',
      humanExplanation: '根据最新架构决策将防截断与纯净 UI 规范固化至工作手册中。',
      command: 'replace_file_content(path="deploy/lobehub/.../AssistantStatusDrawer.tsx")',
      result: '✓ 文件更新成功，SHA-256 乐观锁校验通过。',
      durationMs: 620,
    },
  },
  {
    id: 'act-5',
    dateGroup: 'earlier',
    icon: '✓',
    iconBg: 'rgba(82, 196, 26, 0.12)',
    title: '完成系统全链路冒烟测试',
    summary: '通过端到端生命周期检查，48项契约不变量断言全部通过。',
    timestamp: '9月30日',
    status: 'success',
    toolBadge: 'test',
    detail: {
      stage: 'Verify → Terminal',
      toolName: 'pytest_verify',
      humanExplanation: '全量守护套件运行完成，未检测到破坏性架构偏离。',
      command: 'pytest tests/scenario/test_muse_connector_invariants.py',
      result: '8 passed in 1.42s',
      durationMs: 1420,
    },
  },
];

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
    const [activities] = useState<ActivityItem[]>(DEFAULT_ACTIVITIES);
    const [approvals] = useState<ApprovalRecord[]>(DEFAULT_APPROVALS);
    const [upcomingJobs, setUpcomingJobs] = useState<UpcomingJob[]>(DEFAULT_UPCOMING_JOBS);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    // 活动日志详情弹窗状态
    const [detailModalOpen, setDetailModalOpen] = useState(false);
    const [selectedActivityId, setSelectedActivityId] = useState<string>(DEFAULT_ACTIVITIES[0]?.id || '');

    const selectedActivity = useMemo(
      () => activities.find((a) => a.id === selectedActivityId) || activities[0],
      [activities, selectedActivityId],
    );

    // 拉取后端真值文件列表
    const fetchStandingFiles = useCallback(async () => {
      if (!assistantId) return;
      setLoading(true);
      setErrorMsg(null);
      try {
        const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        const userId =
          (typeof window !== 'undefined' && (window as any)?.__LCA_USER_ID) ||
          process.env.NEXT_PUBLIC_MOCK_DEV_USER_ID ||
          'local-dev-user';
        const url = `/lca-api/v1/assistants/${assistantId}/standing-files`;
        const res = await fetch(url, {
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
            'x-lca-token': token,
            'x-lca-user-id': userId,
          },
        });
        const contentType = res.headers.get('content-type') || '';
        if (!res.ok) {
          if (contentType.includes('application/json')) {
            const errData = await res.json().catch(() => null);
            throw new Error(errData?.error?.detail || `加载失败 (HTTP ${res.status})`);
          }
          throw new Error(`加载失败 (HTTP ${res.status})`);
        }
        if (!contentType.includes('application/json')) {
          throw new Error(`接口返回非 JSON 响应 (HTTP ${res.status})`);
        }
        const data = await res.json();
        setFiles(data.files || []);
      } catch (err: any) {
        setErrorMsg(err.message || '加载配置列表失败');
      } finally {
        setLoading(false);
      }
    }, [assistantId]);

    // 拉取即将到来的任务 (Jobs API)
    const fetchJobs = useCallback(async () => {
      if (!assistantId) return;
      try {
        const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        const url = `/lca-api/v1/assistants/${assistantId}/jobs`;
        const res = await fetch(url, {
          headers: {
            Authorization: `Bearer ${token}`,
            'x-lca-token': token,
          },
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data?.jobs) && data.jobs.length > 0) {
            setUpcomingJobs(
              data.jobs.map((j: any) => ({
                id: j.id,
                title: j.title || '定时提醒',
                schedule: j.schedule,
                timezone: j.timezone || 'Asia/Shanghai',
                enabled: j.enabled !== false,
                body: j.body || '',
                nextRun: '按计划触发',
                delivery: '当前对话',
              })),
            );
          }
        }
      } catch {
        // 使用默认预设
      }
    }, [assistantId]);

    useEffect(() => {
      if (open && assistantId) {
        fetchStandingFiles();
        fetchJobs();
      }
    }, [open, assistantId, fetchStandingFiles, fetchJobs]);

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

    const renderActivityRow = (act: ActivityItem) => (
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
            <span style={{ fontSize: 11, color: '#8c8c8c' }}>{act.timestamp}</span>
          </div>
          <div className={styles.activitySummary}>{act.summary}</div>
          <div className={styles.activityBottom}>
            {act.toolBadge && (
              <Tag color="blue" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>
                {act.toolBadge}
              </Tag>
            )}
            <span>点击查看执行详情 ›</span>
          </div>
        </div>
      </div>
    );

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
            <Button size="small" onClick={fetchStandingFiles} loading={loading}>
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
                        <Switch
                          size="small"
                          checked={job.enabled}
                          onChange={(checked) => handleToggleJob(job.id, checked)}
                        />
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
