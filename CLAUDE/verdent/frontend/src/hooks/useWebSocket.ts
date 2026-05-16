/**
 * useWebSocket — connect to the VERDENT WS server and listen for events.
 *
 * Returns:
 *   connected:   boolean
 *   lastMessage: parsed JSON payload | null
 *   subscribe:   filter messages by event type
 */
import { useEffect, useRef, useState, useCallback } from 'react';

const WS_URL = (import.meta.env.VITE_WS_URL as string | undefined) ?? 'ws://localhost:4000/ws';

export type WsMessage<T = unknown> = {
  event:   string;
  payload: T;
};

export function useWebSocket<T = unknown>(eventFilter?: string) {
  const wsRef                           = useRef<WebSocket | null>(null);
  const [connected, setConnected]       = useState(false);
  const [lastMessage, setLastMessage]   = useState<WsMessage<T> | null>(null);
  const reconnectTimer                  = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      if (eventFilter) {
        ws.send(JSON.stringify({ subscribe: eventFilter }));
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Auto-reconnect after 3 s
      reconnectTimer.current = setTimeout(connect, 3_000);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data as string) as WsMessage<T>;
        if (!eventFilter || msg.event === eventFilter) {
          setLastMessage(msg);
        }
      } catch { /* ignore malformed */ }
    };
  }, [eventFilter]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [connect]);

  return { connected, lastMessage };
}
