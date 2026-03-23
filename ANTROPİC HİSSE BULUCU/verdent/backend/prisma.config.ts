import path from 'node:path'
import { defineConfig } from 'prisma/config'
import dotenv from 'dotenv'

dotenv.config()

const dbUrl = process.env.DATABASE_URL ?? 'postgresql://postgres:password@localhost:5432/verdent_db'

export default defineConfig({
  earlyAccess: true,
  schema: path.join(__dirname, 'prisma/schema.prisma'),
  datasource: {
    url: dbUrl,
  },
  migrate: {
    async adapter() {
      const { PrismaPg } = await import('@prisma/adapter-pg')
      const { default: pg } = await import('pg')
      const pool = new pg.Pool({ connectionString: dbUrl })
      return new PrismaPg(pool)
    },
  },
})
