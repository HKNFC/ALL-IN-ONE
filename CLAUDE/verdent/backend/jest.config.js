/** @type {import('jest').Config} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src/__tests__'],
  testMatch: ['**/*.test.ts'],
  transform: { '^.+\\.ts$': ['ts-jest', { tsconfig: { strict: false } }] },
  moduleFileExtensions: ['ts', 'js', 'json'],
  clearMocks: true,
  coverageDirectory: 'coverage',
  collectCoverageFrom: ['src/services/**/*.ts'],
};
