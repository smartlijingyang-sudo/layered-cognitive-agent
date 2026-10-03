'use client';

import {
  ClockCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  Button,
  DatePicker,
  Flex,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Tag,
  Typography,
  message,
} from 'antd';
import { createStaticStyles } from 'antd-style';
import dayjs from 'dayjs';
import React, { memo, useCallback, useMemo, useState } from 'react';

const { Text, Paragraph } = Typography;

export interface CronTaskCardWidgetPayload {
  widget_name?: string;
  job_id: string;
  title: string;
  body: string;
  schedule_label: string;
  next_run_local?: string | null;
  execution_kind?: string;
  due?: boolean;
  enabled?: boolean;
  delayed_by_seconds?: number | null;
  delivery_status?: 'delivered' | 'failed' | 'silent' | 'not_sent';
  actions?: string[];
}

export interface CronTaskCardProps {
  content?: string;
  payload?: CronTaskCardWidgetPayload;
  assistantId?: string;
  className?: string;
  style?: React.CSSProperties;
}

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    card: css`
      background: ${cssVar.colorBgElevated};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 14px;
      padding: 14px 16px;
      margin: 8px 0;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      overflow: hidden;

      &:hover {
        border-color: ${cssVar.colorPrimaryBorder};
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.07);
      }
    `,
    header: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    `,
    titleRow: css`
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    `,
    iconBadge: css`
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 26px;
      height: 26px;
      border-radius: 8px;
      background: ${cssVar.colorPrimaryBg};
      color: ${cssVar.colorPrimary};
      font-size: 14px;
      flex-shrink: 0;
    `,
    titleText: css`
      font-size: 14px;
      font-weight: 600;
      color: ${cssVar.colorText};
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    `,
    bodyContent: css`
      font-size: 13px;
      color: ${cssVar.colorTextSecondary};
      background: ${cssVar.colorFillQuaternary};
      padding: 10px 12px;
      border-radius: 8px;
      margin-bottom: 10px;
      line-height: 1.6;
    `,
    metaRow: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      color: ${cssVar.colorTextTertiary};
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 6px;
    `,
    actionsRow: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-top: 1px dashed ${cssVar.colorBorderSecondary};
      padding-top: 10px;
      gap: 8px;
      flex-wrap: wrap;
    `,
    snoozeGroup: css`
      display: flex;
      align-items: center;
      gap: 6px;
    `,
    snoozeLabel: css`
      font-size: 11px;
      color: ${cssVar.colorTextTertiary};
      margin-right: 2px;
    `,
    snoozePill: css`
      font-size: 11px;
      height: 24px;
      padding: 0 8px;
      border-radius: 12px;
    `,
    rightActions: css`
      display: flex;
      align-items: center;
      gap: 6px;
    `,
  };
});

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

export const CronTaskCard = memo<CronTaskCardProps>(
  ({ content, payload: directPayload, assistantId: propAssistantId, className, style }) => {
    // 解析嵌入在消息中的 [widget:cron_task_card] JSON
    const parsedPayload = useMemo<CronTaskCardWidgetPayload | null>(() => {
      if (directPayload) return directPayload;
      if (!content) return null;
      const match = content.match(/\[widget:cron_task_card\]\s*(\{[\s\S]*?\})\s*\[\/widget:cron_task_card\]/);
      if (!match) return null;
      try {
        return JSON.parse(match[1]);
      } catch {
        return null;
      }
    }, [content, directPayload]);

    const [isDeleted, setIsDeleted] = useState(false);
    const [statusNote, setStatusNote] = useState<string | null>(null);
    const [isEditOpen, setIsEditOpen] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [form] = Form.useForm();

    if (!parsedPayload || isDeleted) {
      if (isDeleted) {
        return (
          <div className={styles.card} style={style}>
            <Text type="secondary" italic>
              🗑️ 定时任务 [{parsedPayload?.title || '任务'}] 已删除
            </Text>
          </div>
        );
      }
      return null;
    }

    const {
      job_id,
      title,
      body,
      schedule_label,
      delayed_by_seconds,
      enabled = true,
      execution_kind = 'agent',
    } = parsedPayload;

    const assistantId = propAssistantId || 'current';

    // 快捷推迟
    const handleSnooze = useCallback(
      async (minutes: number) => {
        try {
          const res = await fetch(`/lca-api/v1/assistants/${assistantId}/jobs/${job_id}/snooze`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ minutes }),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          message.success(`已为您将任务推迟 ${minutes} 分钟！`);
          setStatusNote(`已推迟 ${minutes} 分钟 (下次: ${data.new_at?.slice(11, 16) || ''})`);
        } catch (err: any) {
          message.error(err?.message || '推迟失败');
        }
      },
      [assistantId, job_id]
    );

    // 删除任务
    const handleDelete = useCallback(async () => {
      try {
        const res = await fetch(`/lca-api/v1/assistants/${assistantId}/jobs/${job_id}`, {
          method: 'DELETE',
          headers: authHeaders(),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setIsDeleted(true);
        message.success('定时任务已删除');
      } catch (err: any) {
        message.error(err?.message || '删除失败');
      }
    }, [assistantId, job_id]);

    // 切换启停
    const handleTogglePause = useCallback(async () => {
      try {
        const res = await fetch(`/lca-api/v1/assistants/${assistantId}/jobs/${job_id}`, {
          method: 'PUT',
          headers: authHeaders(),
          body: JSON.stringify({ enabled: !enabled }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        message.success(enabled ? '任务已暂停' : '任务已重新启用');
        setStatusNote(enabled ? '已暂停' : '已恢复');
      } catch (err: any) {
        message.error(err?.message || '状态切换失败');
      }
    }, [assistantId, job_id, enabled]);

    // 保存编辑
    const handleEditSave = useCallback(async () => {
      try {
        const values = await form.validateFields();
        setSubmitting(true);
        const updateData: Record<string, any> = {
          title: values.title,
          body: values.body,
        };
        if (values.time) {
          updateData.schedule = {
            kind: 'oneshot',
            at: values.time.toISOString(),
          };
        }
        const res = await fetch(`/lca-api/v1/assistants/${assistantId}/jobs/${job_id}`, {
          method: 'PUT',
          headers: authHeaders(),
          body: JSON.stringify(updateData),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        message.success('定时任务已修改');
        setIsEditOpen(false);
        setStatusNote('已修改更新');
      } catch (err: any) {
        message.error(err?.message || '保存失败');
      } finally {
        setSubmitting(false);
      }
    }, [form, assistantId, job_id]);

    const isDelayed = typeof delayed_by_seconds === 'number' && delayed_by_seconds > 60;
    const delayedMinutes = isDelayed ? Math.round(delayed_by_seconds / 60) : 0;

    return (
      <div className={`${styles.card} ${className || ''}`} style={style}>
        {/* 卡片顶栏 */}
        <div className={styles.header}>
          <div className={styles.titleRow}>
            <div className={styles.iconBadge}>
              <ClockCircleOutlined />
            </div>
            <span className={styles.titleText}>{title}</span>
            {isDelayed ? (
              <Tag color="orange" style={{ margin: 0 }}>
                延迟送达 (+{delayedMinutes}m)
              </Tag>
            ) : (
              <Tag color="cyan" style={{ margin: 0 }}>
                {execution_kind === 'agent' ? '🤖 任务已送达' : '⏰ 提醒已送达'}
              </Tag>
            )}
            {statusNote && <Tag color="blue">{statusNote}</Tag>}
          </div>
          <Tag color={enabled ? 'success' : 'default'} style={{ marginRight: 0 }}>
            {enabled ? '活跃' : '已暂停'}
          </Tag>
        </div>

        {/* 任务内容正文 */}
        <div className={styles.bodyContent}>
          <Paragraph ellipsis={{ rows: 3, expandable: true, symbol: '展开' }} style={{ margin: 0 }}>
            {body}
          </Paragraph>
        </div>

        {/* 规则与时区元数据 */}
        <div className={styles.metaRow}>
          <span>⏱️ 设定规则: {schedule_label}</span>
          <span>🎯 任务标识: {job_id}</span>
        </div>

        {/* 交互操作栏 */}
        <div className={styles.actionsRow}>
          {/* 原地快捷推迟 */}
          <div className={styles.snoozeGroup}>
            <span className={styles.snoozeLabel}>
              <ThunderboltOutlined /> 推迟:
            </span>
            <Button size="small" className={styles.snoozePill} onClick={() => handleSnooze(10)}>
              +10m
            </Button>
            <Button size="small" className={styles.snoozePill} onClick={() => handleSnooze(30)}>
              +30m
            </Button>
            <Button size="small" className={styles.snoozePill} onClick={() => handleSnooze(60)}>
              +1h
            </Button>
          </div>

          {/* 右侧管理按钮 */}
          <div className={styles.rightActions}>
            <Button
              size="small"
              icon={enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              onClick={handleTogglePause}
            >
              {enabled ? '暂停' : '恢复'}
            </Button>

            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => {
                form.setFieldsValue({
                  title,
                  body,
                  time: dayjs().add(30, 'minute'),
                });
                setIsEditOpen(true);
              }}
            >
              编辑
            </Button>

            <Popconfirm
              title="确定删除此定时任务吗？"
              description="删除后将不再触发。"
              onConfirm={handleDelete}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </div>
        </div>

        {/* 编辑任务弹窗 */}
        <Modal
          title="✏️ 编辑定时任务"
          open={isEditOpen}
          onOk={handleEditSave}
          onCancel={() => setIsEditOpen(false)}
          confirmLoading={submitting}
          destroyOnClose
        >
          <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
            <Form.Item label="任务标题" name="title" rules={[{ required: true, message: '请输入标题' }]}>
              <Input placeholder="任务名称" />
            </Form.Item>
            <Form.Item label="提醒内容 / 提示词" name="body" rules={[{ required: true, message: '请输入正文' }]}>
              <Input.TextArea rows={3} placeholder="到点提醒或执行的内容" />
            </Form.Item>
            <Form.Item label="调整下次提醒时间" name="time">
              <DatePicker showTime format="YYYY-MM-DD HH:mm" style={{ width: '100%' }} />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    );
  }
);

CronTaskCard.displayName = 'CronTaskCard';

export default CronTaskCard;
