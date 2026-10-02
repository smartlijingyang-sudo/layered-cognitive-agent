'use client';

import {
  Button,
  Drawer,
  Dropdown,
  Empty,
  Flex,
  type MenuProps,
  Segmented,
  Spin,
  Tag,
  Tooltip,
  Typography,
  message as antMessage,
} from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useEffect, useState } from 'react';

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

type SectionKey = 'identity' | 'rules' | 'memory' | 'workspace' | 'connectors';

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
        font-size: 12px;
        padding: 4px 2px;
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
 * 右侧 480px 滑出面板，支持 Identity / Rules / Memory / Workspace / Connectors 五大横向 Tab 切换，
 * 顶部呈现大尺寸动态 Mascot 头像、名称及编辑铅笔快捷菜单，点击自动回填聊天框。
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
                <Tag color="cyan">在线助理</Tag>
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                ID: {assistantId ? assistantId.slice(0, 18) + '...' : '当前活跃助理'}
              </Text>
            </div>
          </div>

          {/* 横向分段选择器 (Identity / Rules / Memory / Workspace / Connectors) */}
          <div className={styles.segmentWrapper}>
            <Segmented<SectionKey>
              value={activeSection}
              onChange={setActiveSection}
              options={[
                { label: '🪪 Identity', value: 'identity' },
                { label: '📋 Rules', value: 'rules' },
                { label: '🧠 Memory', value: 'memory' },
                { label: '📁 Workspace', value: 'workspace' },
                { label: '⚡ Connectors', value: 'connectors' },
              ]}
            />
          </div>

          {/* 内容区 */}
          {activeSection === 'connectors' ? (
            <div className={styles.cardsList}>
              <ConnectorsPanel assistantId={assistantId} />
            </div>
          ) : loading && files.length === 0 ? (
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
