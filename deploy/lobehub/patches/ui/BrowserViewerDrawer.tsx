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

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    drawerBody: css`
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 0 !important;
      background: #141414;
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
      if (customEvent.detail) {
        const { sessionId: sid, url: u, title: t, status: s, takeover } = customEvent.detail;
        setSessionId(sid);
        if (u) setUrl(u);
        if (t) setTitle(t);
        setStatus(takeover ? 'human_takeover' : s || 'idle');
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
        header: { borderBottom: '1px solid rgba(255,255,255,0.1)', padding: '12px 16px' },
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
