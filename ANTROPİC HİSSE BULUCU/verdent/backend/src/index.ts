import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import morgan from 'morgan'
import compression from 'compression'
import dotenv from 'dotenv'
import http from 'http'

import marketRoutes      from './routes/marketRoutes'
import scannerRoutes     from './routes/scannerRoutes'
import backtestRoutes    from './routes/backtestRoutes'
import stockRoutes       from './routes/stockRoutes'
import consistencyRoutes from './routes/consistencyRoutes'
import calibrateRoutes   from './routes/calibrateRoutes'

import { errorHandler }  from './middleware/errorHandler'
import { initWebSocket } from './ws'
import { setupSwagger }  from './swagger'
import { startDataSyncJob } from './jobs/dataSyncJob'

dotenv.config()

const app    = express()
const server = http.createServer(app)
const PORT   = process.env.PORT || 3001

// ── Security & parsing ──────────────────────────────────────────────────────
app.use(helmet())
app.use(cors({ origin: ['http://localhost:3000', 'http://localhost:5173'] }))
app.use(compression())
app.use(morgan('dev'))
app.use(express.json({ limit: '1mb' }))
app.use(express.urlencoded({ extended: true }))

// ── Health check ────────────────────────────────────────────────────────────
app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString(), service: 'VERDENT API' })
})

// ── Routes ──────────────────────────────────────────────────────────────────
app.use('/api/market',      marketRoutes)
app.use('/api/scanner',     scannerRoutes)
app.use('/api/backtest',    backtestRoutes)
app.use('/api/stocks',      stockRoutes)
app.use('/api/consistency', consistencyRoutes)
app.use('/api/calibrate',   calibrateRoutes)

// ── API Docs (Swagger) ───────────────────────────────────────────────────────
setupSwagger(app)

// ── 404 & global error handler ───────────────────────────────────────────────
app.use((_req, res) => {
  res.status(404).json({ error: { message: 'Route not found', code: 'NOT_FOUND', status: 404 } })
})
app.use(errorHandler)

// ── Start ────────────────────────────────────────────────────────────────────
server.listen(PORT, () => {
  console.log(`\n  VERDENT API running on http://localhost:${PORT}`)
  console.log(`  API Docs:  http://localhost:${PORT}/api/docs\n`)
  initWebSocket(server)
  startDataSyncJob()
})

export default app
