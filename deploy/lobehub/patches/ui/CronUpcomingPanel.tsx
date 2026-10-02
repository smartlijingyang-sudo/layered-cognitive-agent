'use client';

import {
  Button,
  Empty,
  Flex,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useEffect, useState } from 'react';

const { Text } = Typography;

export interface CronListItem {
  id: string;
  title: string;
  schedule_label: string;
  next_run_local: string | null;
  due: boolean;
  enabled: boolean;
  last_run_local: string | null;
  last_delivery: 'delivered' | 'failed' | 'silent' | 'not_sent' | null;
}

export interface CronUpcomingPanelProps {
  /** 助理唯一标识（LCA assistant id） */
  assistantId?: string;
  /** 自定义类名 */
  className?: string;
  /** 自定义样式 */
  style?: React.CSSProperties;
}

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    container: css`
      display: flex;
      flex-direction: column;
      gap: 12px;
      height: 100%;
      overflow-y: auto;
      padding: 6px 2px 4px;
    `,
    topSummary: css`
      background: ${cssVar.colorBgElevated};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 12px;
      padding: 10px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    `,
    summaryText: css`
      font-size: 13px;
      font-weight: 500;
      color: ${cssVar.colorText};
    `,
    jobCard: css`
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 12px;
      padding: 12px 14px;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        border-color: ${cssVar.colorPrimaryBorder};
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
      }
    `,
    cardHeader: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    `,
    cardTitle: css`
      font-size: 14px;
      font-weight: 600;
      color: ${cssVar.colorText};
      display: flex;
      align-items: center;
      gap: 6px;
      min-width: 0;
    `,
    titleText: css`
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    `,
    scheduleLabel: css`
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11px;
      color: ${cssVar.colorTextSecondary};
      background: ${cssVar.colorFillTertiary};
      padding: 2px 8px;
      border-radius: 6px;
      display: inline-block;
      margin-bottom: 8px;
    `,
    nextRunRow: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      margin-bottom: 8px;
    `,
    metaRow: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      color: ${cssVar.colorTextTertiary};
      border-top: 1px dashed ${cssVar.colorBorderSecondary};
      padding-top: 8px;
      gap: 8px;
    `,
    hint: css`
      font-size: 11px;
      color: ${cssVar.colorTextQuaternary};
      line-height: 1.5;
      text-align: center;
      padding: 8px 4px;
    `,
  };
});

const LAST_DELIVERY_META: Record<string, { label: string; color: string }> = {
  delivered: { label: '已投递', color: 'success' },
  failed: { label: '投递失败', color: 'error' },
  silent: { label: '静默', color: 'default' },
  not_sent: { label: '未投递', color: 'warning' },
};

export const CronUpcomingPanel = memo<CronUpcomingPanelProps>(
  ({ assistantId, className, style }) => {
    const [jobs, setJobs] = useState<CronListItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    // 拉取后端 cron.list 投影（ADR-0268 §10）。时间一律由服务端算好，
    // 浏览器只渲染 next_run_local 字符串，不自行推算。
    const fetchJobs = useCallback(async () => {
      if (!assistantId) return;
      setLoading(true);
      setErrorMsg(null);
      try {
        const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        const userId =
          (typeof window !== 'undefined' && (window as any)?.__LCA_USER_ID) ||
          process.env.NEXT_PUBLIC_MOCK_DEV_USER_ID ||
          'local-dev-user';
        const url = `/lca-api/v1/assistants/${assistantId}/jobs`;
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
        setJobs(Array.isArray(data?.jobs) ? data.jobs : []);
      } catch (err: any) {
        setErrorMsg(err?.message || '加载即将到来的定时任务失败');
      } finally {
        setLoading(false);
      }
    }, [assistantId]);

    useEffect(() => {
      fetchJobs();
    }, [fetchJobs]);

    const renderJobCard = (job: CronListItem) => {
      const deliveryMeta = job.last_delivery ? LAST_DELIVERY_META[job.last_delivery] : undefined;
      return (
        <div key={job.id} className={styles.jobCard}>
          <div className={styles.cardHeader}>
            <div className={styles.cardTitle}>
              <span className={styles.titleText}>{job.title}</span>
              {job.due && <Tag color="orange">到期</Tag>}
              <Tag color={job.enabled ? 'green' : 'default'}>
                {job.enabled ? '启用' : '停用'}
              </Tag>
            </div>
          </div>
          <div className={styles.scheduleLabel}>{job.schedule_label}</div>
          <div className={styles.nextRunRow}>
            <Text type="secondary">下次运行</Text>
            <Text strong style={{ fontSize: 13 }}>
              {job.next_run_local ?? (job.due ? '立即触发' : '—')}
            </Text>
          </div>
          <div className={styles.metaRow}>
            <Tooltip title="上次运行时间（任务时区墙钟）">
              <span>上次运行: {job.last_run_local ?? '—'}</span>
            </Tooltip>
            {deliveryMeta ? (
              <Tag color={deliveryMeta.color} style={{ marginRight: 0, fontSize: 10 }}>
                {deliveryMeta.label}
              </Tag>
            ) : (
              <span>投递: —</span>
            )}
          </div>
        </div>
      );
    };

    return (
      <div className={`${styles.container} ${className || ''}`} style={style}>
        <div className={styles.topSummary}>
          <div className={styles.summaryText}>
            ⏰ 即将到来
            <Tag color="blue" style={{ marginLeft: 6 }}>
              {jobs.length} 项
            </Tag>
          </div>
          <Button size="small" onClick={fetchJobs} loading={loading}>
            刷新
          </Button>
        </div>

        {loading && jobs.length === 0 ? (
          <Flex justify="center" align="center" style={{ padding: '40px 0' }}>
            <Spin tip="正在读取定时任务..." />
          </Flex>
        ) : errorMsg && jobs.length === 0 ? (
          <Flex justify="center" align="center" style={{ padding: '40px 0' }}>
            <Empty description={errorMsg} />
          </Flex>
        ) : jobs.length === 0 ? (
          <Flex justify="center" align="center" style={{ padding: '40px 0' }}>
            <Empty description="暂无即将到来的定时任务" />
          </Flex>
        ) : (
          jobs.map(renderJobCard)
        )}

        <div className={styles.hint}>
          时间由服务端按任务时区计算，浏览器不自行推算（ADR-0268 §10）
        </div>
      </div>
    );
  },
);

CronUpcomingPanel.displayName = 'CronUpcomingPanel';

export default CronUpcomingPanel;