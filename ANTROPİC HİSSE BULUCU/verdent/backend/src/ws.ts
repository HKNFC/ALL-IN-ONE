import { WebSocketServer, WebSocket } from 'ws'
import type { Server } from 'http'

let wss: WebSocketServer | null = null

export function initWebSocket(server: Server): void {
  wss = new WebSocketServer({ server, path: '/ws' })

  wss.on('connection', (ws: WebSocket) => {
    console.log('[WS] Client connected')

    ws.send(JSON.stringify({ event: 'connected', data: { message: 'VERDENT WebSocket ready' } }))

    ws.on('message', (raw) => {
      try {
        const msg = JSON.parse(raw.toString()) as { event: string; data?: unknown }
        if (msg.event === 'ping') {
          ws.send(JSON.stringify({ event: 'pong', data: { ts: Date.now() } }))
        }
      } catch {
        // ignore malformed messages
      }
    })

    ws.on('close', () => {
      console.log('[WS] Client disconnected')
    })

    ws.on('error', (err) => {
      console.error('[WS] Error:', err.message)
    })
  })

  console.log('[WS] WebSocket server attached to /ws')
}

/**
 * Broadcast a named event to all connected clients.
 * Called from route handlers (e.g. backtest complete, scan done).
 */
export function emitWsEvent(event: string, data: unknown): void {
  if (!wss) return

  const payload = JSON.stringify({ event, data, ts: Date.now() })
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(payload)
    }
  })
}

/**
 * Broadcast backtest progress (0-100) to all clients.
 * Used by BacktestEngine during long-running jobs.
 */
export function emitBacktestProgress(jobId: string, progress: number, message?: string): void {
  emitWsEvent('backtest:progress', { jobId, progress, message })
}
