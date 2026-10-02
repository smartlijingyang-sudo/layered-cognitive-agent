'use client';

import { Button, Card, Tag, Typography, message as antMessage } from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useEffect, useRef, useState } from 'react';

const { Text } = Typography;

export interface ConnectorAuthCardProps {
  /** 连接器名称，如 Gmail / GitHub / Slack / Google Drive */
  appName?: string;
  /** OAuth 授权跳转 URL */
  authUrl?: string;
  /** 连接实例 ID，用于向后端刷新轮询 */
  connectionId?: string;
  /** 自定义卡片标题 */
  title?: string;
  /** 自定义权限/用途说明 */
  description?: string;
  /** 授权成功后的回调 */
  onConnected?: (connectionId: string) => void;
  /** 自定义类名 */
  className?: string;
  /** 自定义样式 */
  style?: React.CSSProperties;
}

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    card: css`
      max-width: 440px;
      margin: 10px 0;
      border-radius: 14px;
      border: 1px solid ${cssVar.colorBorderSecondary};
      background: ${cssVar.colorBgContainer};
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
      transition: all 0.25s ease;
      overflow: hidden;

      &:hover {
        border-color: ${cssVar.colorPrimaryBorder};
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
      }
    `,
    header: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    `,
    brandRow: css`
      display: flex;
      align-items: center;
      gap: 10px;
    `,
    brandIcon: css`
      width: 36px;
      height: 36px;
      border-radius: 9px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: ${cssVar.colorFillQuaternary};
      flex-shrink: 0;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    `,
    brandTitle: css`
      font-size: 15px;
      font-weight: 600;
      line-height: 20px;
      color: ${cssVar.colorText};
    `,
    brandSubtitle: css`
      font-size: 12px;
      color: ${cssVar.colorTextDescription};
      line-height: 16px;
    `,
    body: css`
      font-size: 13px;
      line-height: 20px;
      color: ${cssVar.colorTextSecondary};
      margin-bottom: 14px;
    `,
    footer: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding-top: 10px;
      border-top: 1px solid ${cssVar.colorBorderSecondary};
    `,
    statusRow: css`
      display: flex;
      align-items: center;
      gap: 6px;
    `,
  };
});

/**
 * 品牌 Icon 渲染器
 */
const BrandIcon: React.FC<{ name: string }> = ({ name }) => {
  const norm = name.toLowerCase();

  if (norm.includes('gmail')) {
    return (
      <svg width="22" height="18" viewBox="0 0 24 24" fill="none">
        <path
          d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L12 9.545l8.073-6.052C21.69 2.28 24 3.434 24 5.457z"
          fill="#EA4335"
        />
      </svg>
    );
  }

  if (norm.includes('github')) {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
      </svg>
    );
  }

  if (norm.includes('slack')) {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
        <path
          d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313z"
          fill="#E01E5A"
        />
        <path
          d="M8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312z"
          fill="#36C5F0"
        />
        <path
          d="M18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312z"
          fill="#2EB67D"
        />
        <path
          d="M15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"
          fill="#ECB22E"
        />
      </svg>
    );
  }

  // 默认云端服务插头图标
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 2v6m0 8v6M4.93 4.93l4.24 4.24m5.66 5.66l4.24 4.24M2 12h6m8 0h6M4.93 19.07l4.24-4.24m5.66-5.66l4.24-4.24" />
    </svg>
  );
};

/**
 * 会话流交互式连接器授权卡片 (ConnectorAuthCard)
 *
 * 彻底替换裸露链接，为用户提供一键弹窗授权与自动轮询状态机。
 */
export const ConnectorAuthCard = memo<ConnectorAuthCardProps>(
  ({
    appName = 'Gmail',
    authUrl,
    connectionId,
    title,
    description,
    onConnected,
    className,
    style,
  }) => {
    const [status, setStatus] = useState<'pending' | 'authorizing' | 'connected' | 'error'>('pending');
    const [checking, setChecking] = useState(false);
    const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

    const cardTitle = title || `${appName} 连接器授权`;
    const cardDesc =
      description ||
      `连接到你的 ${appName} 账户以允许助理直接读取、搜索并安全执行相关协作指令。`;

    // 检查连接是否已完成生效
    const checkConnectionStatus = useCallback(
      async (quiet = false): Promise<boolean> => {
        if (!connectionId) return false;
        try {
          setChecking(true);
          const res = await fetch(`/lca-api/composio/connections/${connectionId}/refresh`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer dev_local_token',
              'x-lca-token': 'dev_local_token',
              'x-lca-user-id': 'dev_user',
            },
          });
          if (res.ok) {
            const data = await res.json();
            const connStatus = data?.connection?.status || data?.status;
            if (connStatus === 'ACTIVE' || connStatus === 'CONNECTED' || data?.connected) {
              setStatus('connected');
              if (!quiet) {
                antMessage.success(`🎉 ${appName} 授权成功！助理现已连接。`);
              }
              onConnected?.(connectionId);
              return true;
            }
          }
        } catch {
          // 容错轮询
        } finally {
          setChecking(false);
        }
        return false;
      },
      [connectionId, appName, onConnected],
    );

    // 唤起 OAuth 独立窗口
    const handleStartAuth = useCallback(() => {
      if (!authUrl) return;

      setStatus('authorizing');

      // 居中开启 620 x 720 弹窗
      const w = 620;
      const h = 720;
      const left = window.screen.width / 2 - w / 2;
      const top = window.screen.height / 2 - h / 2;

      const popup = window.open(
        authUrl,
        `OAuth_${appName}`,
        `width=${w},height=${h},top=${top},left=${left},status=no,menubar=no,toolbar=no,location=no`,
      );

      // 启动 2.5s 轮询检测
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      pollTimerRef.current = setInterval(async () => {
        const isDone = await checkConnectionStatus(true);
        if (isDone || (popup && popup.closed)) {
          if (isDone && pollTimerRef.current) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
          }
        }
      }, 2500);
    }, [authUrl, appName, checkConnectionStatus]);

    // 组件卸载时清理定时器
    useEffect(() => {
      return () => {
        if (pollTimerRef.current) {
          clearInterval(pollTimerRef.current);
        }
      };
    }, []);

    return (
      <Card
        className={`${styles.card} ${className || ''}`}
        style={style}
        size="small"
        bordered={false}
      >
        <div className={styles.header}>
          <div className={styles.brandRow}>
            <div className={styles.brandIcon}>
              <BrandIcon name={appName} />
            </div>
            <div>
              <div className={styles.brandTitle}>{cardTitle}</div>
              <div className={styles.brandSubtitle}>Composio 官方安全连接协议</div>
            </div>
          </div>

          <div>
            {status === 'connected' ? (
              <Tag color="success">🟢 已连接</Tag>
            ) : status === 'authorizing' ? (
              <Tag color="processing">⏳ 授权验证中</Tag>
            ) : (
              <Tag color="warning">🟡 待授权</Tag>
            )}
          </div>
        </div>

        <div className={styles.body}>{cardDesc}</div>

        <div className={styles.footer}>
          <div className={styles.statusRow}>
            {status === 'connected' ? (
              <Text type="success" style={{ fontSize: 12 }}>
                ✓ 凭据已持久化就绪
              </Text>
            ) : (
              <Text type="secondary" style={{ fontSize: 12 }}>
                在新打开的窗口中完成登录授权
              </Text>
            )}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            {status === 'authorizing' && (
              <Button
                size="small"
                loading={checking}
                onClick={() => checkConnectionStatus(false)}
              >
                检测状态
              </Button>
            )}

            {status !== 'connected' ? (
              <Button
                type="primary"
                size="small"
                loading={status === 'authorizing' && checking}
                onClick={handleStartAuth}
                disabled={!authUrl}
              >
                {status === 'authorizing' ? '重新打开授权窗' : '立即授权连接'}
              </Button>
            ) : (
              <Button size="small" type="default" disabled>
                已成功绑定
              </Button>
            )}
          </div>
        </div>
      </Card>
    );
  },
);

ConnectorAuthCard.displayName = 'ConnectorAuthCard';

export default ConnectorAuthCard;
