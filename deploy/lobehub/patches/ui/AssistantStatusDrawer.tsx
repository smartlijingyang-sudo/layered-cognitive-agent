'use client';

import { Button, Drawer, Empty, Flex, Segmented, Spin, Tag, Tooltip, Typography } from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useEffect, useState } from 'react';

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

export interface AssistantStatusDrawerProps {
  /** 抽屉是否展开 */
  open: boolean;
  /** 关闭抽屉回调 */
  onClose: () => void;
  /** 助理唯一标识 */
  assistantId?: string;
  /** 助理名称 */
  assistantName?: string;
  /** 点击全屏编辑文件回调 */
  onEditFile?: (filename: string, fileInfo: StandingFileInfo) => void;
  /** 自定义样式类名 */
  className?: string;
}

type SectionKey = 'identity' | 'rules' | 'memory' | 'workspace';

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    drawerBody: css`
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      height: 100%;
      background: ${cssVar.colorBgLayout};
    `,
    headerMeta: css`
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid ${cssVar.colorBorderSecondary};
    `,
    segmentWrapper: css`
      margin-bottom: 16px;
      .ant-segmented {
        background: ${cssVar.colorBgElevated};
        padding: 4px;
        border-radius: 12px;
        width: 100%;
        display: flex;
      }
      .ant-segmented-item {
        flex: 1;
        text-align: center;
        border-radius: 8px;
        font-weight: 500;
      }
    `,
    cardsList: css`
      display: flex;
      flex-direction: column;
      gap: 14px;
      overflow-y: auto;
      flex: 1;
      padding-right: 2px;
    `,
    fileCard: css`
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        border-color: ${cssVar.colorPrimary};
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
        transform: translateY(-1px);
      }
    `,
    cardHeader: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    `,
    cardTitle: css`
      font-weight: 600;
      font-size: 14px;
      display: flex;
      align-items: center;
      gap: 6px;
      color: ${cssVar.colorText};
    `,
    pathRow: css`
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11px;
      color: ${cssVar.colorTextSecondary};
      margin-bottom: 10px;
      word-break: break-all;
      background: ${cssVar.colorFillTertiary};
      padding: 4px 8px;
      border-radius: 6px;
    `,
    summaryBox: css`
      background: ${cssVar.colorFillQuaternary};
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 12px;
      color: ${cssVar.colorTextTertiary};
      margin-bottom: 12px;
      max-height: 90px;
      overflow: hidden;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.5;
    `,
    cardFooter: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      color: ${cssVar.colorTextQuaternary};
    `,
    ssotBanner: css`
      background: linear-gradient(135deg, rgba(200, 231, 255, 0.2) 0%, rgba(240, 238, 250, 0.3) 100%);
      border: 1px solid rgba(20, 115, 200, 0.15);
      border-radius: 12px;
      padding: 12px 14px;
      margin-top: 14px;
      font-size: 12px;
      color: ${cssVar.colorTextSecondary};
      line-height: 1.6;
    `,
  };
});

const FILE_ROLE_METADATA: Record<string, { label: string; icon: string; tagColor: string }> = {
  'IDENTITY.md': { label: '身份与人设', icon: '🪪', tagColor: 'blue' },
  'SOUL.md': { label: '灵魂与红线', icon: '🌟', tagColor: 'purple' },
  'USER.md': { label: '用户画像', icon: '👤', tagColor: 'cyan' },
  'AGENTS.md': { label: '工作手册与血训', icon: '📋', tagColor: 'green' },
  'MEMORY.md': { label: '长期事实', icon: '🧠', tagColor: 'gold' },
};

/**
 * 助理状态与文件真值抽屉组件 (Assistant Status Drawer)
 *
 * 右侧 480px 滑出面板，支持 Identity / Memory / Workspace 三大横向 Section 切换，
 * 呈现 4 大核心 Standing Files 卡片预览与「全屏编辑」触发入口。
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
    const [activeSection, setActiveSection] = useState<SectionKey>('identity');
    const [loading, setLoading] = useState(false);
    const [files, setFiles] = useState<StandingFileInfo[]>([]);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

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
        setErrorMsg(err.message || '加载常驻文件列表失败');
      } finally {
        setLoading(false);
      }
    }, [assistantId]);

    useEffect(() => {
      if (open && assistantId) {
        fetchStandingFiles();
      }
    }, [open, assistantId, fetchStandingFiles]);

    // 分类筛选文件
    const displayedFiles = files.filter((f) => {
      if (activeSection === 'identity') {
        return f.filename === 'IDENTITY.md' || f.filename === 'SOUL.md' || f.filename === 'USER.md';
      }
      if (activeSection === 'rules') {
        return f.filename === 'AGENTS.md';
      }
      if (activeSection === 'memory') {
        return f.filename === 'MEMORY.md';
      }
      return true; // workspace 呈现全部
    });

    const renderCard = (file: StandingFileInfo) => {
      const meta = FILE_ROLE_METADATA[file.filename] || {
        label: '配置文件',
        icon: '📄',
        tagColor: 'default',
      };
      return (
        <div key={file.filename} className={styles.fileCard}>
          <div className={styles.cardHeader}>
            <div className={styles.cardTitle}>
              <span>{meta.icon}</span>
              <span>{file.filename}</span>
              <Tag color={meta.tagColor} style={{ marginLeft: 6 }}>
                {meta.label}
              </Tag>
            </div>
            <Button
              type="primary"
              size="small"
              onClick={() => onEditFile?.(file.filename, file)}
            >
              全屏编辑
            </Button>
          </div>

          <div className={styles.pathRow}>
            <span>{file.path || `~/.lca/assistants/${assistantId}/${file.filename}`}</span>
          </div>

          <div className={styles.summaryBox}>
            {file.summary || (
              <span style={{ fontStyle: 'italic', opacity: 0.6 }}>暂无内容预览</span>
            )}
          </div>

          <div className={styles.cardFooter}>
            <span>
              {file.line_count || 0} 行 · {file.size_bytes || 0} 字节
            </span>
            <Tooltip title={`完整哈希: ${file.content_hash}`}>
              <span style={{ cursor: 'help' }}>
                {file.content_hash ? file.content_hash.slice(0, 16) + '...' : '未初始化'}
              </span>
            </Tooltip>
          </div>
        </div>
      );
    };

    return (
      <Drawer
        title={
          <Flex vertical gap={2}>
            <Title level={5} style={{ margin: 0 }}>
              {assistantName} · 状态与真值中心
            </Title>
            <Text type="secondary" style={{ fontSize: 12 }}>
              File as SSOT · 磁盘唯一真值文件架构
            </Text>
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
          {/* 横向分段选择器 (Identity / Memory / Workspace) */}
          <div className={styles.segmentWrapper}>
            <Segmented<SectionKey>
              value={activeSection}
              onChange={setActiveSection}
              options={[
                { label: '🪪 Identity', value: 'identity' },
                { label: '📋 Rules', value: 'rules' },
                { label: '🧠 Memory', value: 'memory' },
                { label: '📁 Workspace', value: 'workspace' },
              ]}
            />
          </div>

          {/* 内容区 */}
          {loading && files.length === 0 ? (
            <Flex justify="center" align="center" style={{ flex: 1 }}>
              <Spin tip="正在读取磁盘唯一真值文件..." />
            </Flex>
          ) : errorMsg && files.length === 0 ? (
            <Flex justify="center" align="center" style={{ flex: 1 }}>
              <Empty description={errorMsg} />
            </Flex>
          ) : (
            <div className={styles.cardsList}>
              {displayedFiles.map(renderCard)}

              {/* SSOT 架构提示横幅 */}
              <div className={styles.ssotBanner}>
                <Paragraph style={{ margin: 0 }}>
                  <strong>💡 文件即唯一真值源（File as SSOT）：</strong>
                  <br />
                  配置与记忆全部存为纯 Markdown 文件，而非数据库黑盒。
                  双写采用 SHA-256 乐观锁防冲突，编辑保存后即刻原子写盘，下轮对话实时注入生效！
                </Paragraph>
              </div>
            </div>
          )}
        </div>
      </Drawer>
    );
  },
);

AssistantStatusDrawer.displayName = 'AssistantStatusDrawer';

export default AssistantStatusDrawer;
