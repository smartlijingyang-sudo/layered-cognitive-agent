'use client';

import React, { memo, useCallback, useEffect, useState } from 'react';
import { Drawer, Flex, Typography, message } from 'antd';
import { createStaticStyles } from 'antd-style';
import BrowserToolbar from './BrowserToolbar';
import BrowserCanvas from './BrowserCanvas';

const { Text } = Typography;

export interface BrowserDrawerEventDetail {
  sessionId: string;
  url?: string;
  title?: string;
  status?: string;
  takeover?: boolean;
}

const styles = createStaticStyles(({ css }) => {
  return {
    drawerBody: css`
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 0 !important;
      background: #fff;
      overflow: hidden;
    `,
    canvasContainer: css`
      flex: 1;
      width: 100%;
      height: 100%;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    `,
  };
});

export const BrowserViewerDrawer: React.FC = memo(() => {
  const [open, setOpen] = useState<boolean>(false);
  const [sessionId, setSessionId] = useState<string>('');
  const [url, setUrl] = useState<string>('about:blank');
  const [title, setTitle] = useState<string>('Browser Window');
  const [status, setStatus] = useState<string>('idle');

  // 监听来自聊天卡片的打开抽屉事件
  useEffect(() => {
    const handleOpen = (e: Event) => {
      const customEvent = e as CustomEvent<BrowserDrawerEventDetail>;
      const detail = customEvent.detail;
      if (detail) {
        const targetSid = detail.sessionId;
        if (!targetSid || targetSid === 'default') {
          fetch('/lca-api/browser/sessions')
            .then((res) => res.json())
            .then((data) => {
              if (data.sessions && data.sessions.length > 0) {
                setSessionId(data.sessions[0].session_id);
              }
            })
            .catch(() => {});
        } else {
          setSessionId(targetSid);
        }
        if (detail.url) setUrl(detail.url);
        if (detail.title) setTitle(detail.title);
        setStatus(detail.takeover ? 'human_takeover' : detail.status || 'idle');
        setOpen(true);
      }
    };

    window.addEventListener('lca:open_browser_drawer', handleOpen);
    return () => {
      window.removeEventListener('lca:open_browser_drawer', handleOpen);
    };
  }, []);

  const handleNavigate = useCallback(async (newUrl: string) => {
    setUrl(newUrl);
    if (!sessionId) return;
    try {
      await fetch(`/lca-api/browser/sessions/${sessionId}/navigate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: newUrl }),
      });
      message.success('已发送导航请求');
    } catch {
      message.error('导航请求发送失败');
    }
  }, [sessionId]);

  const handleToggleTakeover = useCallback((takeover: boolean) => {
    const newStatus = takeover ? 'human_takeover' : 'idle';
    setStatus(newStatus);
    message.info(takeover ? '已进入人工接管模式，您现在可以直接操控' : '已交还 AI 自动化操控');
  }, []);

  return (
    <Drawer
      title={
        <Flex justify="space-between" align="center" style={{ width: '100%' }}>
          <Text strong style={{ fontSize: 15 }}>
            {title || '实时无头浏览器视口 (Live Headless Browser)'}
          </Text>
        </Flex>
      }
      placement="right"
      width="70vw"
      open={open}
      onClose={() => setOpen(false)}
      destroyOnClose={false}
      classNames={{ body: styles.drawerBody }}
      styles={{
        header: { padding: '12px 16px' },
      }}
    >
      <div className={styles.canvasContainer}>
        <BrowserToolbar
          url={url}
          title={title}
          status={status}
          onNavigate={handleNavigate}
          onToggleTakeover={handleToggleTakeover}
        />
        <div style={{ flex: 1, position: 'relative' }}>
          {sessionId && (
            <BrowserCanvas
              sessionId={sessionId}
              url={url}
              status={status}
              onTakeoverRequest={() => handleToggleTakeover(true)}
              style={{ width: '100%', height: '100%' }}
            />
          )}
        </div>
      </div>
    </Drawer>
  );
});

BrowserViewerDrawer.displayName = 'BrowserViewerDrawer';
export default BrowserViewerDrawer;
