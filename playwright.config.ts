import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const isCI = !!process.env.CI

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 30_000 },
  // Smoke is stable; allow one retry in CI for flake on cold Vite.
  retries: isCI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'artifacts/e2e/playwright-report' }]],
  outputDir: 'artifacts/e2e/test-results',
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
    locale: 'ru-RU',
    reducedMotion: 'reduce',
    navigationTimeout: 90_000,
  },
  // CI: preview after build (stable). Local: vite dev, reuse if already up.
  webServer: isCI
    ? {
        command: 'npx vite preview --host 127.0.0.1 --port 5173 --strictPort',
        url: 'http://127.0.0.1:5173/',
        reuseExistingServer: false,
        timeout: 120_000,
      }
    : {
        command: 'npx vite --host 127.0.0.1 --port 5173 --strictPort',
        url: 'http://127.0.0.1:5173/',
        reuseExistingServer: true,
        timeout: 180_000,
      },
  projects: [
    {
      name: 'chromium-desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
})
