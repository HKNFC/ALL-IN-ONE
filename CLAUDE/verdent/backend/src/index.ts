import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import dotenv from 'dotenv';
import http from 'http';
import swaggerUi from 'swagger-ui-express';

// ── New unified routes ───────────────────────────────────────────────────────
import marketRoutes      from './routes/marketRoutes';
import scannerRoutes     from './routes/scannerRoutes';
import backtestRoutes    from './routes/backtestRoutes';
import stockRoutes       from './routes/stockRoutes';
import consistencyRoutes from './routes/consistencyRoutes';
import diagnosticRoutes  from './routes/diagnosticRoutes';
import calibratorRoutes  from './routes/calibratorRoutes';

// ── Legacy routes (kept to avoid breaking any existing callers) ──────────────
import portfolioRoutes       from './routes/portfolio';
import marketConditionRoutes from './routes/marketCondition';
import criteriaRoutes        from './routes/criteria';

import { attachWS }    from './ws';
import { swaggerSpec } from './swagger';

dotenv.config();

const app    = express();
const PORT   = Number(process.env.PORT) || 4000;
const server = http.createServer(app);

// ── WebSocket server ─────────────────────────────────────────────────────────
const wsServer = attachWS(server);

// ── Middleware ───────────────────────────────────────────────────────────────
app.use(helmet());
app.use(cors({ origin: process.env.FRONTEND_URL || 'http://localhost:3000', credentials: true }));
app.use(morgan('dev'));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ── Swagger UI ───────────────────────────────────────────────────────────────
app.use('/api/docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec, {
  customSiteTitle: 'VERDENT API Docs',
  customCss: '.swagger-ui .topbar { background-color: #000; } .swagger-ui .topbar .download-url-wrapper { display: none; }',
}));

// ── Primary API routes ───────────────────────────────────────────────────────
app.use('/api/market',      marketRoutes);
app.use('/api/scanner',     scannerRoutes);
app.use('/api/backtest',    backtestRoutes);
app.use('/api/stocks',      stockRoutes);
app.use('/api/consistency', consistencyRoutes);
app.use('/api/diagnostic',  diagnosticRoutes);
app.use('/api/calibrate',   calibratorRoutes);

// ── Legacy routes ────────────────────────────────────────────────────────────
app.use('/api/portfolio',        portfolioRoutes);
app.use('/api/market-condition', marketConditionRoutes);
app.use('/api/criteria',         criteriaRoutes);

// ── Health ───────────────────────────────────────────────────────────────────
app.get('/api/health', (_req, res) => {
  res.json({
    status:    'ok',
    timestamp: new Date().toISOString(),
    version:   '1.0.0',
    wsClients: wsServer.clients.size,
  });
});

app.get('/api/jobs/status', (_req, res) => {
  res.json({ jobs: [], message: 'dataSyncJob registered — runs daily after market close' });
});

// ── 404 ──────────────────────────────────────────────────────────────────────
app.use((_req, res) => {
  res.status(404).json({ error: 'Route not found' });
});

// ── Error handler ─────────────────────────────────────────────────────────────
app.use((err: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error', message: err.message });
});

// ── Start ─────────────────────────────────────────────────────────────────────
server.listen(PORT, () => {
  console.log(`\n🚀 VERDENT API  →  http://localhost:${PORT}`);
  console.log(`   Docs         →  http://localhost:${PORT}/api/docs`);
  console.log(`   Health       →  http://localhost:${PORT}/api/health`);
  console.log(`   WebSocket    →  ws://localhost:${PORT}/ws\n`);
});

export default app;
