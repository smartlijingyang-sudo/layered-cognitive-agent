'use client';

import { type CSSProperties, memo, useCallback, useEffect, useRef, useState } from 'react';

type Device = {
  capabilities: string[];
  device_id: string;
  name: string;
  status: string;
};

const encodeKey = (event: KeyboardEvent): string | null => {
  if (event.metaKey || event.altKey) return null;
  if (event.ctrlKey && event.key.length === 1) {
    const code = event.key.toLowerCase().charCodeAt(0);
    if (code >= 97 && code <= 122) return String.fromCharCode(code - 96);
  }
  if (event.key === 'Enter') return '\r';
  if (event.key === 'Backspace') return '\x7f';
  if (event.key === 'Tab') return '\t';
  if (event.key === 'Escape') return '\x1b';
  if (event.key === 'ArrowUp') return '\x1b[A';
  if (event.key === 'ArrowDown') return '\x1b[B';
  if (event.key === 'ArrowRight') return '\x1b[C';
  if (event.key === 'ArrowLeft') return '\x1b[D';
  if (event.key === 'Home') return '\x1b[H';
  if (event.key === 'End') return '\x1b[F';
  if (event.key === 'Delete') return '\x1b[3~';
  if (event.key.length === 1) return event.key;
  return null;
};

const LcaHostConsole = memo(() => {
  const [open, setOpen] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [buffer, setBuffer] = useState('');
  const [status, setStatus] = useState('idle');
  const wsRef = useRef<WebSocket | null>(null);
  const screenRef = useRef<HTMLPreElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      const resp = await fetch('/lca-api/presence/devices');
      if (!resp.ok) return;
      const body = (await resp.json()) as { devices?: Device[] };
      setDevices(Array.isArray(body.devices) ? body.devices : []);
    } catch {
      setDevices([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (screenRef.current) screenRef.current.scrollTop = screenRef.current.scrollHeight;
  }, [buffer]);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  const attach = useCallback(async (deviceId: string) => {
    wsRef.current?.close();
    setBuffer('');
    setStatus('opening');
    const created = await fetch('/lca-api/console/sessions', {
      body: JSON.stringify({ cols: 100, device_id: deviceId, rows: 28 }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    });
    if (!created.ok) {
      setStatus('error');
      setBuffer(`open failed: ${created.status}\n`);
      return;
    }
    const body = (await created.json()) as { session_id: string };
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${window.location.host}/lca-api/console/sessions/${body.session_id}`);
    wsRef.current = ws;
    ws.onopen = () => setStatus('connected');
    ws.onclose = () => setStatus('closed');
    ws.onerror = () => setStatus('error');
    ws.onmessage = (event) => {
      try {
        const frame = JSON.parse(String(event.data)) as { data?: string; type?: string };
        if (frame.type === 'output' && frame.data) {
          setBuffer((prev) => (prev + frame.data).slice(-200_000));
        }
        if (frame.type === 'exit') setStatus('exit');
      } catch {
        /* ignore malformed frames */
      }
    };
  }, []);

  const online = devices.find((item) => item.status === 'online');

  return (
    <>
      <button
        onClick={() => {
          setOpen((value) => !value);
          if (!open && online) void attach(online.device_id);
        }}
        style={fabStyle}
        type="button"
      >
        {online ? '本机终端' : '终端离线'}
      </button>
      {open ? (
        <div style={panelStyle}>
          <div style={headerStyle}>
            <span>{online ? `${online.name} · ${status}` : 'host sidecar 未连接'}</span>
            <button
              onClick={() => {
                wsRef.current?.close();
                setOpen(false);
              }}
              type="button"
            >
              关闭
            </button>
          </div>
          <pre
            onKeyDown={(event) => {
              const data = encodeKey(event.nativeEvent);
              if (!data || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
              event.preventDefault();
              wsRef.current.send(JSON.stringify({ data, type: 'input' }));
            }}
            ref={screenRef}
            style={screenStyle}
            tabIndex={0}
          >
            {buffer || (online ? '点击此区域后开始输入' : '启动栈后会自动连上本机 host')}
          </pre>
        </div>
      ) : null}
    </>
  );
});

LcaHostConsole.displayName = 'LcaHostConsole';

export default LcaHostConsole;

const fabStyle: CSSProperties = {
  background: '#111',
  border: '1px solid #444',
  borderRadius: 999,
  bottom: 20,
  color: '#eee',
  cursor: 'pointer',
  fontSize: 13,
  padding: '8px 14px',
  position: 'fixed',
  right: 20,
  zIndex: 1200,
};

const panelStyle: CSSProperties = {
  background: '#0b0b0b',
  border: '1px solid #333',
  borderRadius: 10,
  bottom: 64,
  boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
  display: 'flex',
  flexDirection: 'column',
  height: 360,
  position: 'fixed',
  right: 20,
  width: 640,
  zIndex: 1200,
};

const headerStyle: CSSProperties = {
  alignItems: 'center',
  color: '#ddd',
  display: 'flex',
  fontSize: 12,
  justifyContent: 'space-between',
  padding: '8px 12px',
};

const screenStyle: CSSProperties = {
  color: '#d4d4d4',
  flex: 1,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  fontSize: 12,
  margin: 0,
  overflow: 'auto',
  padding: 12,
  whiteSpace: 'pre-wrap',
};
