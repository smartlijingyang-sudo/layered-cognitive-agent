'use client';

import {
  Button,
  Card,
  Collapse,
  Empty,
  Flex,
  Input,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message as antMessage,
} from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';

const { Text, Title, Paragraph } = Typography;

export interface ConnectorItem {
  id: string;
  name: string;
  category: 'cloud' | 'local';
  description: string;
  iconType: 'gmail' | 'googledrive' | 'github' | 'slack' | 'notion' | 'companion';
  connected: boolean;
  enabledForAssistant: boolean;
  connectionId?: string;
  authUrl?: string;
  tools: { name: string; description: string }[];
}

export interface ConnectorsPanelProps {
  /** 助理唯一标识 */
  assistantId?: string;
  /** 自定义类名 */
  className?: string;
  /** 自定义样式 */
  style?: React.CSSProperties;
}

const DEFAULT_CONNECTORS: ConnectorItem[] = [
  {
    id: 'gmail',
    name: 'Gmail',
    category: 'cloud',
    description: 'Google Gmail 官方邮件系统集成，支持收件箱阅读、多维检索、草稿编排与自动化处理。',
    iconType: 'gmail',
    connected: false,
    enabledForAssistant: true,
    tools: [
      { name: 'GMAIL_FETCH_EMAILS', description: '获取邮件详情，建议显式指定 max_results 避免空跑' },
      { name: 'GMAIL_LIST_THREADS', description: '概览邮件线程列表（推荐列表查询首选）' },
      { name: 'GMAIL_GET_THREAD', description: '获取指定邮件会话线程完整往来记录' },
      { name: 'GMAIL_SEND_MESSAGE', description: '直接通过 Gmail 发送邮件' },
      { name: 'GMAIL_CREATE_DRAFT', description: '创建邮件草稿供人工确认' },
      { name: 'GMAIL_LIST_MESSAGES', description: '列出邮件消息简要摘要' },
      { name: 'GMAIL_SEARCH_PEOPLE', description: '检索 Google 联系人' },
      { name: 'GMAIL_ADD_LABEL_TO_EMAIL', description: '为邮件附加标签' },
      { name: 'GMAIL_REMOVE_LABEL_FROM_EMAIL', description: '移除邮件标签' },
      { name: 'GMAIL_BATCH_DELETE_EMAILS', description: '批量移入垃圾箱' },
    ],
  },
  {
    id: 'googledrive',
    name: 'Google Drive',
    category: 'cloud',
    description: 'Google Drive 云端硬盘，支持文件树遍历、文档检索与跨团队资产协同。',
    iconType: 'googledrive',
    connected: false,
    enabledForAssistant: true,
    tools: [
      { name: 'GOOGLEDRIVE_SEARCH_FILES', description: '根据关键词或 MIME 检索云端文件' },
      { name: 'GOOGLEDRIVE_GET_FILE', description: '读取并导出指定云端文件内容' },
      { name: 'GOOGLEDRIVE_CREATE_FILE', description: '在指定目录下创建新文件' },
      { name: 'GOOGLEDRIVE_LIST_PERMISSIONS', description: '查看文件共享权限' },
    ],
  },
  {
    id: 'github',
    name: 'GitHub',
    category: 'cloud',
    description: 'GitHub 源码与工程协作平台，支持代码仓库探查、Issues/PR 协同与文件审查。',
    iconType: 'github',
    connected: false,
    enabledForAssistant: true,
    tools: [
      { name: 'GITHUB_SEARCH_REPOSITORIES', description: '搜索 GitHub 仓库与开源项目' },
      { name: 'GITHUB_GET_FILE_CONTENTS', description: '读取特定分支的代码与文件内容' },
      { name: 'GITHUB_CREATE_ISSUE', description: '创建新的 Issue 跟踪问题' },
      { name: 'GITHUB_CREATE_PULL_REQUEST', description: '创建 PR 提交代码变更' },
      { name: 'GITHUB_LIST_COMMITS', description: '查看仓库提交历史日志' },
    ],
  },
  {
    id: 'slack',
    name: 'Slack',
    category: 'cloud',
    description: 'Slack 团队即时通信平台，支持频道检索、消息交互与异步通知推送。',
    iconType: 'slack',
    connected: false,
    enabledForAssistant: false,
    tools: [
      { name: 'SLACK_SEND_MESSAGE', description: '向指定 Slack 频道发送结构化通知' },
      { name: 'SLACK_LIST_CHANNELS', description: '列出工作区内所有公开/私有频道' },
      { name: 'SLACK_SEARCH_MESSAGES', description: '在 Slack 历史聊天记录中检索上下文' },
    ],
  },
  {
    id: 'notion',
    name: 'Notion',
    category: 'cloud',
    description: 'Notion 模块化知识库与文档系统，支持页面读取、数据库检索与知识库沉淀。',
    iconType: 'notion',
    connected: false,
    enabledForAssistant: false,
    tools: [
      { name: 'NOTION_SEARCH', description: '在全局 Notion 页面和数据库中检索' },
      { name: 'NOTION_GET_PAGE', description: '获取指定 Notion 页面完整 Block 结构' },
      { name: 'NOTION_QUERY_DATABASE', description: '查询结构化数据库记录' },
    ],
  },
  {
    id: 'companion',
    name: '本机 Companion',
    category: 'local',
    description: 'ADR-0246 机器执行边界客户端，支持受限的本地终端 Shell 命令执行与工作区读写。',
    iconType: 'companion',
    connected: true,
    enabledForAssistant: true,
    tools: [
      { name: 'local_runCommand', description: '在已配对的本地机器上执行受限 Shell 指令' },
      { name: 'local_readFile', description: '读取本地主机工作区内文件内容' },
      { name: 'local_writeFile', description: '向本地主机指定文件写入内容' },
      { name: 'local_listDir', description: '枚举本地主机指定目录文件树' },
    ],
  },
];

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    container: css`
      display: flex;
      flex-direction: column;
      gap: 12px;
    `,
    topSummary: css`
      background: ${cssVar.colorBgElevated};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 12px;
      padding: 12px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 4px;
    `,
    summaryText: css`
      font-size: 13px;
      font-weight: 500;
      color: ${cssVar.colorText};
    `,
    connectorCard: css`
      background: ${cssVar.colorBgContainer};
      border: 1px solid ${cssVar.colorBorderSecondary};
      border-radius: 12px;
      padding: 14px 16px;
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
      margin-bottom: 8px;
    `,
    brandBlock: css`
      display: flex;
      align-items: center;
      gap: 10px;
    `,
    iconBox: css`
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: ${cssVar.colorFillQuaternary};
      flex-shrink: 0;
    `,
    brandName: css`
      font-size: 14px;
      font-weight: 600;
      color: ${cssVar.colorText};
      display: flex;
      align-items: center;
      gap: 6px;
    `,
    cardDesc: css`
      font-size: 12px;
      color: ${cssVar.colorTextSecondary};
      line-height: 18px;
      margin-bottom: 10px;
    `,
    cardControls: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-top: 10px;
      border-top: 1px solid ${cssVar.colorBorderSecondary};
    `,
    switchRow: css`
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: ${cssVar.colorTextTertiary};
    `,
    toolsCollapse: css`
      margin-top: 10px;
      background: transparent !important;
      border: none !important;

      .ant-collapse-item {
        border: none !important;
      }
      .ant-collapse-header {
        padding: 4px 0 !important;
        font-size: 12px !important;
        color: ${cssVar.colorPrimary} !important;
      }
      .ant-collapse-content-box {
        padding: 8px 0 !important;
      }
    `,
    toolChip: css`
      display: inline-block;
      margin: 3px;
      padding: 2px 8px;
      border-radius: 6px;
      background: ${cssVar.colorFillTertiary};
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 11px;
      color: ${cssVar.colorText};
    `,
  };
});

/**
 * 品牌图标组件
 */
const ConnectorIcon: React.FC<{ type: string }> = ({ type }) => {
  switch (type) {
    case 'gmail':
      return (
        <svg width="20" height="16" viewBox="0 0 24 24" fill="none">
          <path
            d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L12 9.545l8.073-6.052C21.69 2.28 24 3.434 24 5.457z"
            fill="#EA4335"
          />
        </svg>
      );
    case 'googledrive':
      return (
        <svg width="20" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M8.2 2L13.8 12L8.2 22L2.6 12L8.2 2Z" fill="#0066DA" />
          <path d="M8.2 2L19.4 2L22.2 7L13.8 12L8.2 2Z" fill="#00AC47" />
          <path d="M13.8 12L22.2 7L24 12L18.4 22L8.2 22L13.8 12Z" fill="#FFBA00" />
        </svg>
      );
    case 'github':
      return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
        </svg>
      );
    case 'slack':
      return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path
            d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313z"
            fill="#E01E5A"
          />
          <path
            d="M8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312z"
            fill="#36C5F0"
          />
        </svg>
      );
    case 'notion':
      return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.093-.373L17.765 1.78c-.466-.373-1.073-.653-2.193-.56L2.313 2.293c-.42.046-.513.326-.326.56l2.472 1.355zm-.886 3.125v13.626c0 .886.42 1.258 1.446 1.165l14.428-.84c1.026-.046 1.213-.653 1.213-1.446V6.166c0-.7-.42-1.026-1.12-1.026l-14.848.886c-.746.046-1.12.466-1.12 1.307zm14.195.98v11.339c0 .42-.187.56-.56.56-.28 0-.466-.093-.7-.326l-7.794-9.332v9.332c0 .42-.233.56-.606.56h-1.026c-.373 0-.56-.14-.56-.56V8.587c0-.42.187-.56.56-.56.28 0 .513.14.746.373l7.747 9.285V8.313c0-.42.233-.56.606-.56h1.026c.373 0 .56.14.56.56z" />
        </svg>
      );
    case 'companion':
    default:
      return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <line x1="8" y1="21" x2="16" y2="21" />
          <line x1="12" y1="17" x2="12" y2="21" />
        </svg>
      );
  }
};

/**
 * 右侧抽屉全局连接器中枢面板 (Connectors Panel in Status Drawer)
 */
export const ConnectorsPanel = memo<ConnectorsPanelProps>(({ assistantId, className, style }) => {
  const [connectors, setConnectors] = useState<ConnectorItem[]>(DEFAULT_CONNECTORS);
  const [loading, setLoading] = useState(false);
  const [filterKeyword, setFilterKeyword] = useState('');

  // 拉取后端真实连接状态
  const refreshConnections = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/lca-api/composio/connections', {
        headers: {
          Authorization: 'Bearer dev_local_token',
          'x-lca-token': 'dev_local_token',
          'x-lca-user-id': 'dev_user',
        },
      });
      if (res.ok) {
        const data = await res.json();
        const activeApps = new Set<string>();
        if (Array.isArray(data?.connections)) {
          for (const conn of data.connections) {
            if (conn.status === 'ACTIVE' || conn.status === 'CONNECTED') {
              activeApps.add((conn.appName || '').toLowerCase());
            }
          }
        }

        setConnectors((prev) =>
          prev.map((item) => {
            if (item.category === 'cloud') {
              const isConn = activeApps.has(item.id.toLowerCase());
              return { ...item, connected: isConn };
            }
            return item;
          }),
        );
      }
    } catch {
      // 容错降级使用默认态
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshConnections();
  }, [refreshConnections]);

  // 助理连接器启用开关切换
  const handleToggleAssistant = useCallback((id: string, enabled: boolean) => {
    setConnectors((prev) =>
      prev.map((c) => (c.id === id ? { ...c, enabledForAssistant: enabled } : c)),
    );
    antMessage.info(enabled ? `已为当前助理启用该连接器工具` : `已停用该连接器工具`);
  }, []);

  // 触发连接授权
  const handleConnect = useCallback(
    async (item: ConnectorItem) => {
      if (item.id === 'companion') {
        antMessage.success('本机 Companion 客户端已在线常驻运行！');
        return;
      }
      try {
        setLoading(true);
        const res = await fetch(`/lca-api/composio/connect/${item.id}`, {
          method: 'POST',
          headers: {
            Authorization: 'Bearer dev_local_token',
            'x-lca-token': 'dev_local_token',
            'x-lca-user-id': 'dev_user',
          },
        });
        if (res.ok) {
          const data = await res.json();
          if (data?.authUrl) {
            window.open(data.authUrl, `OAuth_${item.name}`, 'width=620,height=720');
            antMessage.info(`已开启 ${item.name} 授权窗口，完成授权后点击“刷新状态”`);
          }
        } else {
          antMessage.warning(`正在引导发起 ${item.name} 授权，请稍候`);
        }
      } catch {
        antMessage.error(`发起授权失败，请检查网络或配置`);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const connectedCount = useMemo(
    () => connectors.filter((c) => c.connected).length,
    [connectors],
  );

  const filteredConnectors = useMemo(() => {
    if (!filterKeyword.trim()) return connectors;
    const kw = filterKeyword.toLowerCase().trim();
    return connectors.filter(
      (c) =>
        c.name.toLowerCase().includes(kw) ||
        c.description.toLowerCase().includes(kw) ||
        c.tools.some((t) => t.name.toLowerCase().includes(kw)),
    );
  }, [connectors, filterKeyword]);

  return (
    <div className={`${styles.container} ${className || ''}`} style={style}>
      {/* 顶部统计与刷新栏 */}
      <div className={styles.topSummary}>
        <div className={styles.summaryText}>
          ⚡ 全局连接器生态：
          <Tag color="success" style={{ marginLeft: 6 }}>
            已连接 {connectedCount} / {connectors.length}
          </Tag>
        </div>
        <Button size="small" onClick={refreshConnections} loading={loading}>
          刷新状态
        </Button>
      </div>

      {/* 搜索过滤栏 */}
      <Input
        size="small"
        placeholder="搜索连接器名称或工具 (如 Gmail, GitHub...)"
        value={filterKeyword}
        onChange={(e) => setFilterKeyword(e.target.value)}
        allowClear
        style={{ marginBottom: 6 }}
      />

      {/* 连接器卡片列表 */}
      {filteredConnectors.length === 0 ? (
        <Empty description="未找到匹配的连接器" style={{ margin: '30px 0' }} />
      ) : (
        filteredConnectors.map((item) => (
          <div key={item.id} className={styles.connectorCard}>
            <div className={styles.cardHeader}>
              <div className={styles.brandBlock}>
                <div className={styles.iconBox}>
                  <ConnectorIcon type={item.iconType} />
                </div>
                <div>
                  <div className={styles.brandName}>
                    {item.name}
                    <Tag color={item.category === 'local' ? 'purple' : 'blue'} style={{ fontSize: 10 }}>
                      {item.category === 'local' ? '本机' : '云端'}
                    </Tag>
                  </div>
                </div>
              </div>

              <div>
                {item.connected ? (
                  <Tag color="success">🟢 已连接</Tag>
                ) : (
                  <Tag color="default">⚪ 未连接</Tag>
                )}
              </div>
            </div>

            <div className={styles.cardDesc}>{item.description}</div>

            {/* 工具清单折叠面板 */}
            <Collapse
              className={styles.toolsCollapse}
              items={[
                {
                  key: '1',
                  label: `查看 ${item.tools.length} 项可用能力工具清单 ▾`,
                  children: (
                    <div>
                      {item.tools.map((t) => (
                        <Tooltip key={t.name} title={t.description}>
                          <span className={styles.toolChip}>{t.name}</span>
                        </Tooltip>
                      ))}
                    </div>
                  ),
                },
              ]}
            />

            {/* 底部控制栏 */}
            <div className={styles.cardControls}>
              <div className={styles.switchRow}>
                <span>助理使用许可：</span>
                <Switch
                  size="small"
                  checked={item.enabledForAssistant}
                  onChange={(checked) => handleToggleAssistant(item.id, checked)}
                />
              </div>

              <div>
                {!item.connected ? (
                  <Button
                    size="small"
                    type="primary"
                    onClick={() => handleConnect(item)}
                    loading={loading}
                  >
                    立即连接
                  </Button>
                ) : (
                  <Button
                    size="small"
                    type="text"
                    style={{ color: '#52c41a' }}
                    onClick={() => refreshConnections()}
                  >
                    ✓ 运行中
                  </Button>
                )}
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
});

ConnectorsPanel.displayName = 'ConnectorsPanel';

export default ConnectorsPanel;
