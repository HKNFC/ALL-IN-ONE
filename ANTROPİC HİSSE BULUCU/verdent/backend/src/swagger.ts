import swaggerJSDoc from 'swagger-jsdoc'
import swaggerUi from 'swagger-ui-express'
import type { Express } from 'express'

const options: swaggerJSDoc.Options = {
  definition: {
    openapi: '3.0.0',
    info: {
      title:       'VERDENT API',
      version:     '1.0.0',
      description: 'Financial trading analysis platform – market conditions, stock screening, backtesting',
    },
    servers: [
      { url: 'http://localhost:3001', description: 'Local development' },
    ],
    tags: [
      { name: 'Market',      description: 'Market condition analysis' },
      { name: 'Scanner',     description: 'Stock screening with ALFA/BETA/DELTA criteria' },
      { name: 'Backtest',    description: 'Historical strategy backtesting' },
      { name: 'Stocks',      description: 'Stock price and fundamental data' },
      { name: 'Consistency', description: 'Scanner vs backtest consistency checks' },
    ],
    components: {
      schemas: {
        BacktestConfig: {
          type: 'object',
          required: ['criteriaType', 'startDate', 'endDate'],
          properties: {
            name:            { type: 'string', example: 'ALFA Bull Run 2023' },
            criteriaType:    { type: 'string', enum: ['ALFA', 'BETA', 'DELTA', 'HYBRID'] },
            startDate:       { type: 'string', example: '2022-01-03' },
            endDate:         { type: 'string', example: '2024-12-31' },
            rebalancePeriod: { type: 'string', enum: ['WEEKLY', 'MONTHLY'], default: 'MONTHLY' },
            market:          { type: 'string', enum: ['BIST', 'US', 'BOTH'], default: 'US' },
            initialCapital:  { type: 'number', default: 100000 },
            transactionCost: { type: 'number', default: 0.001 },
            slippage:        { type: 'number', default: 0.001 },
          },
        },
        Error: {
          type: 'object',
          properties: {
            error: {
              type: 'object',
              properties: {
                message: { type: 'string' },
                code:    { type: 'string' },
                status:  { type: 'integer' },
              },
            },
          },
        },
      },
    },
  },
  apis: ['./src/routes/*.ts'],
}

export const swaggerSpec = swaggerJSDoc(options)

export function setupSwagger(app: Express): void {
  app.use(
    '/api/docs',
    swaggerUi.serve,
    swaggerUi.setup(swaggerSpec, {
      customSiteTitle: 'VERDENT API Docs',
      customCss: `
        .swagger-ui .topbar { background-color: #0f172a; }
        .swagger-ui .topbar-wrapper .link { color: #00D084; }
      `,
    })
  )

  // Raw spec endpoint
  app.get('/api/docs.json', (_req, res) => {
    res.setHeader('Content-Type', 'application/json')
    res.send(swaggerSpec)
  })

  console.log('[Swagger] API docs available at /api/docs')
}
