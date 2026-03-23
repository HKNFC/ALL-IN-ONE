import { PrismaClient } from '@prisma/client'
import { PrismaPg } from '@prisma/adapter-pg'
import pg from 'pg'

declare global {
  // eslint-disable-next-line no-var
  var __prisma: PrismaClient | undefined
}

function createPrismaClient(): PrismaClient {
  const dbUrl = process.env.DATABASE_URL ?? 'postgresql://postgres:postgres@localhost:5432/verdent_db'
  const pool = new pg.Pool({ connectionString: dbUrl })
  const adapter = new PrismaPg(pool)
  return new PrismaClient({ adapter } as ConstructorParameters<typeof PrismaClient>[0])
}

export const prisma: PrismaClient = global.__prisma ?? createPrismaClient()

if (process.env.NODE_ENV !== 'production') {
  global.__prisma = prisma
}
