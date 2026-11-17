import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

// Unit tests only. Playwright suites live in e2e/ and must never be collected
// by Vitest (Vitest 4 no longer merges the CLI --exclude with its defaults).
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      exclude: ['e2e/**', 'node_modules/**', 'dist/**', 'artifacts/**'],
    },
  }),
)
