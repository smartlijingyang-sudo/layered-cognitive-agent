'use client';

import {
  ClockCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  Button,
  DatePicker,
  Empty,
  Flex,
  Form,
  Input,
  Modal,
  Popconfirm,
  Segmented,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { createStaticStyles } from 'antd-style';
import dayjs from 'dayjs';
import React, { memo, useCallback, useEffect, useState } from 'react';

const { Text, Paragraph } = Typography;

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
      padding: 6px 4px 12px;
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
      font-weight: 600;
      color: ${cssVar.colorText};
      display: flex;
      align-items: center;
      gap: 6px;
    `,
    jobCard: css`
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 12px;
      padding: 12px 14px;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      flex-direction: column;
      gap: 8px;

      &:hover {
        border-color: ${cssVar.colorPrimaryBorder};
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06);
      }
    `,
    cardHeader: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    `,
    cardTitle: css`
      font-size: 13px;
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
      align-self: flex-start;
    `,
    nextRunRow: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
    `,
    metaRow: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      color: ${cssVar.colorTextTertiary};
      border-top: 1px dashed ${cssVar.colorBorderSecondary};
      padding-top: 6px;
      gap: 8px;
    `,
    actionsRow: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-top: 1px solid ${cssVar.colorBorderSecondary};
      padding-top: 8px;
      gap: 6px;
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

function authHeaders(): Record<string, string> {
  const envToken =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env?.NEXT_PUBLIC_LCA_TOKEN
      : undefined;
  const token = envToken || 'lca-local';
  const mockDevUserId =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env?.NEXT_PUBLIC_MOCK_DEV_USER_ID
      : undefined;
  const userId =
    (typeof window !== 'undefined' && (window as any)?.__LCA_USER_ID) ||
    mockDevUserId ||
    'local-dev-user';
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
    'x-lca-token': token,
    'x-lca-user-id': userId,
  };
}

export const CronUpcomingPanel = memo<CronUpcomingPanelProps>(
  ({ assistantId, className, style }) => {
    const [jobs, setJobs] = useState<CronListItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    // 弹窗状态
    const [modalOpen, setModalOpen] = useState(false);
    const [editingJob, setEditingJob] = useState<CronListItem | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const [form] = Form.useForm();

    const fetchJobs = useCallback(async () => {
      if (!assistantId) return;
      setLoading(true);
      setErrorMsg(null);
      try {
        const url = `/lca-api/v1/assistants/${assistantId}/jobs`;
        const res = await fetch(url, { headers: authHeaders() });
        if (!res.ok) {
          throw new Error(`加载失败 (HTTP ${res.status})`);
        }
        const data = await res.json();
        setJobs(Array.isArray(data?.jobs) ? data.jobs : []);
      } catch (err: any) {
        setErrorMsg(err?.message || '加载定时任务失败');
      } finally {
        setLoading(false);
      }
    }, [assistantId]);

    useEffect(() => {
      fetchJobs();

      const onJobsUpdated = () => {
        fetchJobs();
      };
      const onActivityUpdated = (e: any) => {
        const patch = e.detail || e;
        if (patch?.category === 'cron' || patch?.toolName?.startsWith?.('cron.')) {
          fetchJobs();
        }
      };

      if (typeof window !== 'undefined') {
        window.addEventListener('lca:jobs_updated', onJobsUpdated);
        window.addEventListener('lca:run_completed', onJobsUpdated);
        window.addEventListener('lca:status_refresh', onJobsUpdated);
        window.addEventListener('lca:activity_updated', onActivityUpdated);
      }

      // 8 秒静默轮询保持与后端同步
      const timer = setInterval(() => {
        if (!document.hidden) {
          fetchJobs();
        }
      }, 8000);

      return () => {
        clearInterval(timer);
        if (typeof window !== 'undefined') {
          window.removeEventListener('lca:jobs_updated', onJobsUpdated);
          window.removeEventListener('lca:run_completed', onJobsUpdated);
          window.removeEventListener('lca:status_refresh', onJobsUpdated);
          window.removeEventListener('lca:activity_updated', onActivityUpdated);
        }
      };
    }, [fetchJobs]);

    // 手动立即触发一次 (Run Now)
    const handleRunNow = useCallback(
      async (jobId: string) => {
        try {
          message.loading({ content: '正在触发立即执行...', key: 'run-job' });
          const res = await fetch(`/lca-api/v1/assistants/${assistantId}/jobs/${jobId}/run`, {
            method: 'POST',
            headers: authHeaders(),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          message.success({ content: '任务已立即触发执行！', key: 'run-job' });
          fetchJobs();
        } catch (err: any) {
          message.error({ content: err?.message || '立即执行失败', key: 'run-job' });
        }
      },
      [assistantId, fetchJobs]
    );

    // 切换任务启停
    const handleToggleEnable = useCallback(
      async (jobId: string, currentEnabled: boolean) => {
        try {
          const res = await fetch(`/lca-api/v1/assistants/${assistantId}/jobs/${jobId}`, {
            method: 'PUT',
            headers: authHeaders(),
            body: JSON.stringify({ enabled: !currentEnabled }),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          message.success(!currentEnabled ? '任务已启用' : '任务已暂停');
          fetchJobs();
        } catch (err: any) {
          message.error(err?.message || '操作失败');
        }
      },
      [assistantId, fetchJobs]
    );

    // 删除任务
    const handleDelete = useCallback(
      async (jobId: string) => {
        try {
          const res = await fetch(`/lca-api/v1/assistants/${assistantId}/jobs/${jobId}`, {
            method: 'DELETE',
            headers: authHeaders(),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          message.success('定时任务已删除');
          fetchJobs();
        } catch (err: any) {
          message.error(err?.message || '删除失败');
        }
      },
      [assistantId, fetchJobs]
    );

    // 打开编辑弹窗
    const handleOpenEdit = useCallback(
      (job: CronListItem) => {
        setEditingJob(job);
        form.setFieldsValue({
          title: job.title,
          time: dayjs().add(15, 'minute'),
        });
        setModalOpen(true);
      },
      [form]
    );

    // 打开新建弹窗
    const handleOpenCreate = useCallback(() => {
      setEditingJob(null);
      form.resetFields();
      form.setFieldsValue({
        type: 'reminder',
        title: '',
        body: '',
        time: dayjs().add(15, 'minute'),
      });
      setModalOpen(true);
    }, [form]);

    // 提交弹窗保存
    const handleModalSubmit = useCallback(async () => {
      try {
        const values = await form.validateFields();
        setSubmitting(true);

        if (editingJob) {
          // 编辑更新
          const updateData: Record<string, any> = {
            title: values.title,
          };
          if (values.body) updateData.body = values.body;
          if (values.time) {
            updateData.schedule = {
              kind: 'oneshot',
              at: values.time.toISOString(),
            };
          }
          const res = await fetch(
            `/lca-api/v1/assistants/${assistantId}/jobs/${editingJob.id}`,
            {
              method: 'PUT',
              headers: authHeaders(),
              body: JSON.stringify(updateData),
            }
          );
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          message.success('定时任务已更新');
        } else {
          // 新建任务
          const jobId = `job-${Date.now().toString(36)}`;
          const payload = {
            id: jobId,
            title: values.title,
            body: values.body || values.title,
            chat_id: assistantId || 'default',
            timezone: 'Asia/Shanghai',
            schedule: {
              kind: 'oneshot',
              at: (values.time || dayjs().add(15, 'minute')).toISOString(),
            },
            execution: { kind: 'agent' },
            report: 'always',
          };
          const res = await fetch(`/lca-api/v1/assistants/${assistantId}/jobs`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(payload),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          message.success('新定时任务已创建');
        }

        setModalOpen(false);
        fetchJobs();
      } catch (err: any) {
        message.error(err?.message || '保存失败');
      } finally {
        setSubmitting(false);
      }
    }, [form, editingJob, assistantId, fetchJobs]);

    const renderJobCard = (job: CronListItem) => {
      const deliveryMeta = job.last_delivery ? LAST_DELIVERY_META[job.last_delivery] : undefined;
      return (
        <div key={job.id} className={styles.jobCard}>
          <div className={styles.cardHeader}>
            <div className={styles.cardTitle}>
              <span className={styles.titleText}>{job.title}</span>
              {job.due && <Tag color="orange">到期</Tag>}
            </div>
            <Switch
              size="small"
              checked={job.enabled}
              onChange={() => handleToggleEnable(job.id, job.enabled)}
            />
          </div>

          <div className={styles.scheduleLabel}>{job.schedule_label}</div>

          <div className={styles.nextRunRow}>
            <Text type="secondary">下次运行</Text>
            <Text strong style={{ fontSize: 12 }}>
              {job.next_run_local ?? (job.due ? '立即触发' : '—')}
            </Text>
          </div>

          <div className={styles.metaRow}>
            <Tooltip title="上次运行时间（任务时区墙钟）">
              <span>上次: {job.last_run_local ?? '—'}</span>
            </Tooltip>
            {deliveryMeta ? (
              <Tag color={deliveryMeta.color} style={{ marginRight: 0, fontSize: 10 }}>
                {deliveryMeta.label}
              </Tag>
            ) : (
              <span>投递: —</span>
            )}
          </div>

          <div className={styles.actionsRow}>
            <Tooltip title="手动立即执行一次">
              <Button
                size="small"
                type="text"
                icon={<ThunderboltOutlined />}
                onClick={() => handleRunNow(job.id)}
              >
                立即执行
              </Button>
            </Tooltip>

            <Space size={4}>
              <Button
                size="small"
                type="text"
                icon={<EditOutlined />}
                onClick={() => handleOpenEdit(job)}
              >
                编辑
              </Button>

              <Popconfirm
                title="确定删除此定时任务吗？"
                description="删除后将永久不再触发。"
                onConfirm={() => handleDelete(job.id)}
                okText="删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button size="small" type="text" danger icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            </Space>
          </div>
        </div>
      );
    };

    return (
      <div className={`${styles.container} ${className || ''}`} style={style}>
        {/* 顶部仪表板 */}
        <div className={styles.topSummary}>
          <div className={styles.summaryText}>
            ⏰ 即将到来
            <Tag color="blue" style={{ marginLeft: 6 }}>
              {jobs.length} 项
            </Tag>
          </div>
          <Space size={6}>
            <Button size="small" icon={<PlusOutlined />} onClick={handleOpenCreate}>
              新建
            </Button>
            <Button size="small" icon={<ReloadOutlined />} onClick={fetchJobs} loading={loading}>
              刷新
            </Button>
          </Space>
        </div>

        {/* 列表主体 */}
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

        {/* 新建/编辑任务弹窗 */}
        <Modal
          title={editingJob ? '✏️ 编辑定时任务' : '✨ 新建定时任务'}
          open={modalOpen}
          onOk={handleModalSubmit}
          onCancel={() => setModalOpen(false)}
          confirmLoading={submitting}
          destroyOnClose
        >
          <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
            <Form.Item label="任务标题" name="title" rules={[{ required: true, message: '请输入任务标题' }]}>
              <Input placeholder="例如：提醒李超开会 / 晨报抓取" />
            </Form.Item>
            <Form.Item label="提醒内容 / 执行指令" name="body">
              <Input.TextArea rows={3} placeholder="到点提醒或执行的具体内容..." />
            </Form.Item>
            <Form.Item label="触发时间" name="time">
              <DatePicker showTime format="YYYY-MM-DD HH:mm" style={{ width: '100%' }} />
            </Form.Item>
            <div style={{ display: 'flex', gap: 8, marginTop: -12, marginBottom: 16 }}>
              <Button size="small" onClick={() => form.setFieldValue('time', dayjs().add(10, 'minute'))}>
                +10分钟
              </Button>
              <Button size="small" onClick={() => form.setFieldValue('time', dayjs().add(1, 'hour'))}>
                +1小时
              </Button>
              <Button size="small" onClick={() => form.setFieldValue('time', dayjs().add(1, 'day').hour(9).minute(0))}>
                明天 09:00
              </Button>
            </div>
          </Form>
        </Modal>
      </div>
    );
  }
);

CronUpcomingPanel.displayName = 'CronUpcomingPanel';

export default CronUpcomingPanel;