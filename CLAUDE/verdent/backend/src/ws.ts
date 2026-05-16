/**
 * VERDENT — WebSocket server + typed event emitter.
 *
 * Attach to an existing http.Server:
 *   import { attachWS } from './ws';
 *   attachWS(httpServer);
 *
 * Emit events from any route/service:
 *   import { wsEvents } from './ws';
 *   wsEvents.emit('backtest:progress', { id, progress: 42 });
 *
 * Client events (sent TO server):
 *   { type: 'subscribe', channel: 'backtest' | 'market' | 'scan' }
 *   { type: 'ping' }
 *
 * Server events (sent TO clients):
 *   backtest:progress  { id, progress, message }
 *   backtest:complete  { id, result }
 *   backtest:failed    { id, error }
 *   scan:complete      { id, result }
 *   market:update      { market, condition, score, confidence }
 *   pong               {}
 */

import { EventEmitter } from 'events';
import { Server as HttpServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';

// ─── Typed event map ──────────────────────────────────────────────────────────

type WSEventMap = {
  'backtest:progress': { id: string; progress: number; message: string; stage?: string; currentDate?: Date };
  'backtest:complete': { id: string; result: unknown };
  'backtest:failed':   { id: string; error: string };
  'scan:complete':     { id: string; result: unknown };
  'market:update':     { market: string; condition: string; score: number; confidence: number };
  'pong':              Record<string, never>;
};

type WSEventName = keyof WSEventMap;

// ─── Typed emitter ────────────────────────────────────────────────────────────

class WsEventEmitter extends EventEmitter {
  emit<K extends WSEventName>(event: K, payload: WSEventMap[K]): boolean {
    return super.emit(event, payload);
  }
  on<K extends WSEventName>(event: K, listener: (payload: WSEventMap[K]) => void): this {
    return super.on(event, listener);
  }
}

export const wsEvents = new WsEventEmitter();

// ─── Client state ─────────────────────────────────────────────────────────────

interface ClientMeta {
  channels: Set<string>;
  alive:    boolean;
}

const clients = new Map<WebSocket, ClientMeta>();

function broadcast<K extends WSEventName>(event: K, payload: WSEventMap[K], channel?: string): void {
  const msg = JSON.stringify({ type: event, payload, ts: Date.now() });
  for (const [ws, meta] of clients.entries()) {
    if (ws.readyState !== WebSocket.OPEN) continue;
    if (channel && !meta.channels.has(channel) && !meta.channels.has('*')) continue;
    ws.send(msg);
  }
}

// ─── Attach to HTTP server ────────────────────────────────────────────────────

export function attachWS(server: HttpServer): WebSocketServer {
  const wss = new WebSocketServer({ server, path: '/ws' });

  // Forward internal events → WebSocket broadcast
  wsEvents.on('backtest:progress', p  => broadcast('backtest:progress', p, 'backtest'));
  wsEvents.on('backtest:complete', p  => broadcast('backtest:complete', p, 'backtest'));
  wsEvents.on('backtest:failed',   p  => broadcast('backtest:failed',   p, 'backtest'));
  wsEvents.on('scan:complete',     p  => broadcast('scan:complete',     p, 'scan'));
  wsEvents.on('market:update',     p  => broadcast('market:update',     p, 'market'));

  wss.on('connection', (ws: WebSocket) => {
    const meta: ClientMeta = { channels: new Set(['*']), alive: true };
    clients.set(ws, meta);

    ws.on('message', (raw: Buffer) => {
      try {
        const msg = JSON.parse(raw.toString()) as { type: string; channel?: string };
        if (msg.type === 'subscribe' && msg.channel) {
          meta.channels.delete('*');
          meta.channels.add(msg.channel);
          ws.send(JSON.stringify({ type: 'subscribed', channel: msg.channel }));
        } else if (msg.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong', payload: {}, ts: Date.now() }));
        }
      } catch { /* ignore malformed */ }
    });

    ws.on('pong', () => { meta.alive = true; });
    ws.on('close', () => clients.delete(ws));
    ws.send(JSON.stringify({ type: 'connected', payload: { version: '1.0.0' }, ts: Date.now() }));
  });

  // Heartbeat — remove dead connections every 30 s
  setInterval(() => {
    for (const [ws, meta] of clients.entries()) {
      if (!meta.alive) { ws.terminate(); clients.delete(ws); continue; }
      meta.alive = false;
      ws.ping();
    }
  }, 30_000);

  console.log('[WS] WebSocket server attached on /ws');
  return wss;
}

export function getConnectedCount(): number { return clients.size; }
