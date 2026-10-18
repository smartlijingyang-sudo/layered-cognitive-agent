'use client';

import React, { memo, useCallback, useEffect, useRef, useState } from 'react';
import { createStaticStyles } from 'antd-style';
import { Button, Spin, Typography } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';

const { Text } = Typography;

export interface BrowserCanvasProps {
  sessionId: string;
  url?: string;
  status: string;
  onTakeoverRequest?: () => void;
  className?: string;
  style?: React.CSSProperties;
}

const styles = createStaticStyles(({ css }) => {
  return {
    container: css`
      position: relative;
      width: 100%;
      height: 100%;
      min-height: 480px;
      background: #fff;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 8px;
    `,
    empty: css`
      position: absolute;
      inset: 0;
      z-index: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      color: #595959;
      font-size: 13px;
      line-height: 1.6;
      pointer-events: none;
    `,
    canvas: css`
      display: block;
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      cursor: crosshair;
    `,
    overlay: css`
      position: absolute;
      top: 12px;
      right: 12px;
      background: #fff;
      border: 1px solid #e5e5e5;
      border-radius: 8px;
      padding: 8px 12px;
      display: flex;
      align-items: center;
      gap: 8px;
      z-index: 10;
    `,
    hud: css`
      position: absolute;
      bottom: 12px;
      left: 12px;
      background: #fff;
      border: 1px solid #e5e5e5;
      padding: 4px 10px;
      border-radius: 6px;
      color: #595959;
      font-size: 11px;
      font-family: monospace;
      pointer-events: none;
    `,
  };
});

export const BrowserCanvas: React.FC<BrowserCanvasProps> = memo(({
  sessionId,
  url,
  status,
  onTakeoverRequest,
  className,
  style,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [fps, setFps] = useState<number>(0);
  const [connected, setConnected] = useState<boolean>(false);
  const [hasFrame, setHasFrame] = useState<boolean>(false);
  const frameCountRef = useRef<number>(0);
  const lastFpsTimeRef = useRef<number>(Date.now());

  const isTakeover = status === 'human_takeover';

  // 连接 WebSocket 双向流
  useEffect(() => {
    setHasFrame(false);
    if (!sessionId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const query = url ? `?url=${encodeURIComponent(url)}` : '';
    const wsUrl = `${protocol}//${host}/lca-api/browser/sessions/${sessionId}/stream${query}`;

    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onclose = () => {
      setConnected(false);
    };

    ws.onmessage = async (event: MessageEvent) => {
      if (typeof event.data === 'string') {
        // 元数据文本帧
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'metadata') {
            // URL or title updated
          }
        } catch {
          // ignore
        }
      } else if (event.data instanceof ArrayBuffer) {
        // 二进制画面帧
        const buf = new Uint8Array(event.data);
        if (buf.length > 1 && buf[0] === 0x01) {
          const imgBytes = buf.subarray(1);
          const blob = new Blob([imgBytes], { type: 'image/jpeg' });

          try {
            const imgBitmap = await createImageBitmap(blob);
            const canvas = canvasRef.current;
            if (canvas) {
              if (canvas.width !== imgBitmap.width || canvas.height !== imgBitmap.height) {
                canvas.width = imgBitmap.width;
                canvas.height = imgBitmap.height;
              }
              const ctx = canvas.getContext('2d');
              if (ctx) {
                ctx.drawImage(imgBitmap, 0, 0);
                setHasFrame(true);
                try {
                  sessionStorage.setItem(`lca_browser_drawer_auto_opened_${sessionId}`, '1');
                } catch {
                  // private mode
                }
              }
            }
            imgBitmap.close();

            // 发送 ACK 维持背压平衡
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'ack' }));
            }

            // 计算 FPS
            frameCountRef.current += 1;
            const now = Date.now();
            if (now - lastFpsTimeRef.current >= 1000) {
              setFps(frameCountRef.current);
              frameCountRef.current = 0;
              lastFpsTimeRef.current = now;
            }
          } catch (err) {
            // Bitmap decode error
          }
        }
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [sessionId, url]);

  // 发送上行键鼠事件 (INV-BROWSER-06 归一化坐标)
  const sendInputEvent = useCallback((type: string, e: React.MouseEvent<HTMLCanvasElement>) => {
    const ws = wsRef.current;
    const canvas = canvasRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !canvas) return;

    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;

    // 归一化坐标 [0.0, 1.0]
    const normX = Math.max(0.0, Math.min(1.0, (e.clientX - rect.left) / rect.width));
    const normY = Math.max(0.0, Math.min(1.0, (e.clientY - rect.top) / rect.height));

    let btn: string | undefined = undefined;
    if (e.button === 0) btn = 'left';
    else if (e.button === 1) btn = 'middle';
    else if (e.button === 2) btn = 'right';

    ws.send(JSON.stringify({
      type: 'input',
      event: {
        type,
        x: normX,
        y: normY,
        button: btn,
      },
    }));
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isTakeover) return;
    sendInputEvent('mouse_down', e);
  }, [isTakeover, sendInputEvent]);

  const handleMouseUp = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isTakeover) return;
    sendInputEvent('mouse_up', e);
  }, [isTakeover, sendInputEvent]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isTakeover) return;
    sendInputEvent('mouse_move', e);
  }, [isTakeover, sendInputEvent]);

  return (
    <div className={styles.container} style={style}>
      {!hasFrame && (
        <div className={styles.empty}>
          {!connected && <Spin size="large" />}
          <div style={{ marginTop: connected ? 0 : 12 }}>
            {connected ? '页面还没有画面' : '正在连接浏览器画面'}
          </div>
        </div>
      )}

      <canvas
        ref={canvasRef}
        className={styles.canvas}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseMove={handleMouseMove}
        onContextMenu={(e) => e.preventDefault()}
      />

      <div className={styles.overlay}>
        {isTakeover ? (
          <Text style={{ color: '#52c41a', fontSize: 12, fontWeight: 500 }}>
            ● 人工接管操控中 (Live Control)
          </Text>
        ) : (
          <>
            <Text style={{ color: '#faad14', fontSize: 12 }}>
              ● AI 独占运行 (穿透监控)
            </Text>
            {onTakeoverRequest && (
              <Button
                size="small"
                type="primary"
                icon={<ThunderboltOutlined />}
                onClick={onTakeoverRequest}
                style={{ fontSize: 11, height: 24, padding: '0 8px' }}
              >
                立即接管
              </Button>
            )}
          </>
        )}
      </div>

      {connected && (
        <div className={styles.hud}>
          CDP 串流 | 帧率: {fps} fps | 状态: {status}
        </div>
      )}
    </div>
  );
});

BrowserCanvas.displayName = 'BrowserCanvas';
export default BrowserCanvas;
