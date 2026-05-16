/**
 * OpenAPI / Swagger specification for VERDENT API v1.
 * Served via swagger-ui-express at GET /api/docs
 */

export const swaggerSpec = {
  openapi: '3.0.3',
  info: {
    title:   'VERDENT API',
    version: '1.0.0',
    description: 'Financial trading analysis platform — market conditions, stock scanning, backtesting.',
    contact: { name: 'VERDENT Team' },
  },
  servers: [
    { url: 'http://localhost:4000', description: 'Local dev' },
  ],
  tags: [
    { name: 'Market',      description: 'Market condition analysis' },
    { name: 'Scanner',     description: 'Stock screening / scanning' },
    { name: 'Backtest',    description: 'Historical portfolio backtesting' },
    { name: 'Stocks',      description: 'Stock data, indicators, fundamentals' },
    { name: 'Consistency', description: 'Cross-module consistency checks' },
    { name: 'System',      description: 'Health, jobs, WebSocket info' },
  ],
  paths: {
    // ── Market ─────────────────────────────────────────────────────────────
    '/api/market/condition/{market}': {
      get: {
        tags: ['Market'], summary: 'Current market condition',
        parameters: [{ name: 'market', in: 'path', required: true, schema: { type: 'string', enum: ['BIST','US'] } }],
        responses: { 200: { description: 'MarketConditionResult' } },
      },
    },
    '/api/market/condition/{market}/{date}': {
      get: {
        tags: ['Market'], summary: 'Historical market condition for a specific date',
        parameters: [
          { name: 'market', in: 'path', required: true, schema: { type: 'string', enum: ['BIST','US'] } },
          { name: 'date',   in: 'path', required: true, schema: { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$' } },
        ],
        responses: { 200: { description: 'MarketConditionResult or DB record' } },
      },
    },
    '/api/market/indicators/{market}': {
      get: {
        tags: ['Market'], summary: 'Detailed indicator breakdown',
        parameters: [{ name: 'market', in: 'path', required: true, schema: { type: 'string', enum: ['BIST','US'] } }],
        responses: { 200: { description: 'Indicators object with trend/momentum/volatility/breadth' } },
      },
    },
    '/api/market/history/{market}': {
      get: {
        tags: ['Market'], summary: 'Paginated condition history',
        parameters: [
          { name: 'market', in: 'path', required: true, schema: { type: 'string', enum: ['BIST','US'] } },
          { name: 'limit',  in: 'query', schema: { type: 'integer', default: 30, maximum: 365 } },
          { name: 'offset', in: 'query', schema: { type: 'integer', default: 0 } },
        ],
        responses: { 200: { description: 'Array of MarketCondition records' } },
      },
    },
    '/api/market/breadth/{market}': {
      get: {
        tags: ['Market'], summary: 'Advance/Decline, % above 200 SMA, new highs/lows',
        parameters: [{ name: 'market', in: 'path', required: true, schema: { type: 'string', enum: ['BIST','US'] } }],
        responses: { 200: { description: 'BreadthData object' } },
      },
    },
    '/api/market/index/{index}': {
      get: {
        tags: ['Market'], summary: 'Latest index value',
        parameters: [{ name: 'index', in: 'path', required: true, schema: { type: 'string', enum: ['BIST100','SP500','VIX'] } }],
        responses: { 200: { description: 'IndexData' } },
      },
    },

    // ── Scanner ─────────────────────────────────────────────────────────────
    '/api/scanner/scan': {
      post: {
        tags: ['Scanner'], summary: 'Run a stock scan',
        requestBody: {
          required: true,
          content: { 'application/json': { schema: { $ref: '#/components/schemas/ScanBody' } } },
        },
        responses: { 201: { description: 'ScanResult with top 5 stocks' } },
      },
    },
    '/api/scanner/results': {
      get: {
        tags: ['Scanner'], summary: 'List saved scan results',
        parameters: [
          { name: 'criteria', in: 'query', schema: { type: 'string', enum: ['ALFA','BETA','DELTA'] } },
          { name: 'market',   in: 'query', schema: { type: 'string', enum: ['BIST','US'] } },
          { name: 'limit',    in: 'query', schema: { type: 'integer', default: 20 } },
          { name: 'offset',   in: 'query', schema: { type: 'integer', default: 0 } },
        ],
        responses: { 200: { description: 'Paginated scan results' } },
      },
    },
    '/api/scanner/results/{id}': {
      get: {
        tags: ['Scanner'], summary: 'Get a specific scan result',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: 'StoredScan' }, 404: { description: 'Not found' } },
      },
      delete: {
        tags: ['Scanner'], summary: 'Delete a scan result',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: 'Deleted' } },
      },
    },

    // ── Backtest ────────────────────────────────────────────────────────────
    '/api/backtest/run': {
      post: {
        tags: ['Backtest'], summary: 'Start a new backtest (async)',
        requestBody: {
          required: true,
          content: { 'application/json': { schema: { $ref: '#/components/schemas/BacktestConfig' } } },
        },
        responses: { 202: { description: '{ backtestId, status: "PENDING" }' } },
      },
    },
    '/api/backtest/status/{id}': {
      get: {
        tags: ['Backtest'], summary: 'Poll backtest run status',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: '{ id, status, progress, error }' } },
      },
    },
    '/api/backtest/results': {
      get: {
        tags: ['Backtest'], summary: 'List all backtests (not deleted)',
        parameters: [
          { name: 'criteriaType', in: 'query', schema: { type: 'string', enum: ['ALFA','BETA','DELTA','HYBRID'] } },
          { name: 'market',       in: 'query', schema: { type: 'string', enum: ['BIST','US','BOTH'] } },
          { name: 'status',       in: 'query', schema: { type: 'string', enum: ['PENDING','RUNNING','COMPLETED','FAILED'] } },
          { name: 'limit',        in: 'query', schema: { type: 'integer', default: 20 } },
          { name: 'offset',       in: 'query', schema: { type: 'integer', default: 0 } },
        ],
        responses: { 200: { description: 'Paginated backtest list' } },
      },
    },
    '/api/backtest/results/{id}': {
      get: {
        tags: ['Backtest'], summary: 'Full backtest result detail',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: 'BacktestResult or job status' } },
      },
    },
    '/api/backtest/{id}': {
      delete: {
        tags: ['Backtest'], summary: 'Soft-delete a backtest',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: '{ deleted: id }' } },
      },
    },

    // ── Stocks ──────────────────────────────────────────────────────────────
    '/api/stocks/search': {
      get: {
        tags: ['Stocks'], summary: 'Search stocks by symbol or name',
        parameters: [
          { name: 'q',      in: 'query', required: true, schema: { type: 'string' } },
          { name: 'market', in: 'query', schema: { type: 'string', enum: ['BIST','US'] } },
          { name: 'limit',  in: 'query', schema: { type: 'integer', default: 10 } },
        ],
        responses: { 200: { description: 'Array of matching stocks' } },
      },
    },
    '/api/stocks/list/{market}': {
      get: {
        tags: ['Stocks'], summary: 'All stocks in a market',
        parameters: [{ name: 'market', in: 'path', required: true, schema: { type: 'string', enum: ['BIST','US'] } }],
        responses: { 200: { description: 'Paginated stock list' } },
      },
    },
    '/api/stocks/{symbol}': {
      get: {
        tags: ['Stocks'], summary: 'Stock info',
        parameters: [{ name: 'symbol', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: 'Stock record' } },
      },
    },
    '/api/stocks/{symbol}/price': {
      get: {
        tags: ['Stocks'], summary: 'OHLCV price history',
        parameters: [
          { name: 'symbol',   in: 'path',  required: true, schema: { type: 'string' } },
          { name: 'start',    in: 'query', schema: { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$' } },
          { name: 'end',      in: 'query', schema: { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$' } },
          { name: 'interval', in: 'query', schema: { type: 'string', enum: ['1d','1wk','1mo'], default: '1d' } },
        ],
        responses: { 200: { description: 'OHLCV[]' } },
      },
    },
    '/api/stocks/{symbol}/indicators': {
      get: {
        tags: ['Stocks'], summary: 'All technical indicators for symbol',
        parameters: [{ name: 'symbol', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: 'TechnicalIndicators object' } },
      },
    },
    '/api/stocks/{symbol}/fundamentals': {
      get: {
        tags: ['Stocks'], summary: 'Fundamental data',
        parameters: [{ name: 'symbol', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: 'Fundamentals object' } },
      },
    },

    // ── Consistency ─────────────────────────────────────────────────────────
    '/api/consistency/check': {
      get: {
        tags: ['Consistency'], summary: 'Compare scanner vs backtest for same date/criteria',
        parameters: [
          { name: 'criteria', in: 'query', required: true, schema: { type: 'string', enum: ['ALFA','BETA','DELTA'] } },
          { name: 'date',     in: 'query', required: true, schema: { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$' } },
          { name: 'market',   in: 'query', required: true, schema: { type: 'string', enum: ['BIST','US'] } },
        ],
        responses: {
          200: {
            description: 'Consistency report',
            content: { 'application/json': { schema: {
              type: 'object',
              properties: {
                isConsistent: { type: 'boolean' },
                differences:  { type: 'array', items: { type: 'string' } },
                scanResult:   { type: 'array' },
                backtestSnapshot: { type: 'object', nullable: true },
              },
            } } },
          },
        },
      },
    },

    // ── System ──────────────────────────────────────────────────────────────
    '/api/health': {
      get: {
        tags: ['System'], summary: 'Health check',
        responses: { 200: { description: '{ status, timestamp, version, wsClients }' } },
      },
    },
    '/api/jobs/status': {
      get: {
        tags: ['System'], summary: 'Data sync job status',
        responses: { 200: { description: 'Job registry snapshot' } },
      },
    },
  },
  components: {
    schemas: {
      ScanBody: {
        type: 'object', required: ['criteria','date','market'],
        properties: {
          criteria: { type: 'string', enum: ['ALFA','BETA','DELTA'] },
          date:     { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$', example: '2024-01-15' },
          market:   { type: 'string', enum: ['BIST','US'] },
        },
      },
      BacktestConfig: {
        type: 'object', required: ['name','criteriaType','startDate','endDate','rebalancePeriod','market'],
        properties: {
          name:            { type: 'string', example: 'My HYBRID Test' },
          criteriaType:    { type: 'string', enum: ['ALFA','BETA','DELTA','HYBRID'] },
          startDate:       { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$', example: '2022-01-01' },
          endDate:         { type: 'string', pattern: '^\\d{4}-\\d{2}-\\d{2}$', example: '2024-01-01' },
          rebalancePeriod: { type: 'string', enum: ['WEEKLY','MONTHLY'] },
          market:          { type: 'string', enum: ['BIST','US','BOTH'] },
          initialCapital:  { type: 'number', default: 100000, minimum: 1000 },
          transactionCost: { type: 'number', default: 0.001 },
          slippage:        { type: 'number', default: 0.001 },
        },
      },
    },
  },
};
