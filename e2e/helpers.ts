import { expect, type ConsoleMessage, type Page, type Response } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

export const SCREEN_DIR = path.resolve('artifacts/e2e/screenshots')
export const API_BASE = process.env.E2E_API_URL || 'http://127.0.0.1:8000'

export const RIXOS_BELEK = {
  // Curated catalog id (H50K export is optional and not present in clean checkouts).
  id: 'oh-curated-000169',
  name: 'Rixos Premium Belek',
  city: 'Белек',
  country: 'Турция',
  lat: 36.84505,
  lon: 31.09338,
}

export const KAZAN_MSG =
  'Составь маршрут по Казани на один день: Кремль, прогулка, интересное место поесть, вернуться к 20:00'

export const ISTANBUL_SIX_WISHES_MSG =
  'Стамбул на 1 день с 10:00: достопримечательности, музей, смотровая, ресторан, кофе, вечером бар'

export const HOTEL_CTX_MSG =
  'Мы с ребёнком. Хотим старый город, пляж и хороший ресторан. Вернуться в отель до 19:00.'

export function ensureDirs() {
  fs.mkdirSync(SCREEN_DIR, { recursive: true })
  fs.mkdirSync(path.resolve('artifacts/e2e'), { recursive: true })
}

export async function shot(page: Page, name: string) {
  ensureDirs()
  await page.screenshot({ path: path.join(SCREEN_DIR, `${name}.png`), fullPage: false })
}

export type AuditCollectors = {
  consoleErrors: string[]
  pageErrors: string[]
  failedResponses: string[]
}

export function attachCollectors(page: Page): AuditCollectors {
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const failedResponses: string[] = []

  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      // MapLibre / tile noise that is non-fatal
      if (/favicon|Download the React DevTools/i.test(text)) return
      consoleErrors.push(text)
    }
  })
  page.on('pageerror', (err) => {
    pageErrors.push(String(err))
  })
  page.on('response', (res: Response) => {
    const status = res.status()
    const url = res.url()
    if (status >= 400) {
      // Ignore common benign assets
      if (/favicon|chrome-extension/i.test(url)) return
      failedResponses.push(`${status} ${url}`)
    }
  })

  return { consoleErrors, pageErrors, failedResponses }
}

export async function sendTripMessage(page: Page, text: string) {
  const box = page.locator('textarea').first()
  await expect(box).toBeVisible()
  await box.fill(text)
  await page.getByRole('button', { name: 'Отправить' }).click()
}

export async function waitForTripReady(page: Page, timeout = 180_000) {
  // Prefer waiting for map canvas or day chips after assistant finishes.
  // NOTE: in "map" mode the panel shows only the map (no "День N" chips),
  // so a finished assistant summary ("Маршрут по …", "Добавил …", "Убрал …")
  // together with the rendered map also means ready.
  await page.waitForFunction(
    () => {
      const body = document.body.innerText
      const busy = /Понимаю пожелания|Обновляю маршрут|Ищу места|Проверяю расстояния|Собираю маршрут|Строю маршрут|Считаю маршрут/.test(
        body,
      )
      if (busy) return false
      const hasPlan = /День 1|План поездки/.test(body)
      const hasMap = Boolean(document.querySelector('.maplibregl-canvas, canvas'))
      const hasSummary = /Маршрут по|Маршрут готов|Добавил|Убрал|Заменил|Транспорт/.test(body)
      // Mobile auto-switches to the map tab after plan; chat (summary) is
      // display:none so innerText won't include it — treat map markers as ready.
      const markerCount = document.querySelectorAll(
        '.maplibregl-marker, [aria-label="Map marker"], button[aria-label="Map marker"]',
      ).length
      const failed =
        /Не могу выдумать места|Не удалось|Недостаточно подтверждённых мест|ambiguous_destination|city_not_found/.test(
          body,
        )
      return failed || hasPlan || (hasMap && hasSummary) || (hasMap && markerCount >= 1)
    },
    { timeout },
  )
  const body = await page.locator('body').innerText()
  if (
    /Не могу выдумать места|Не удалось|Недостаточно подтверждённых мест|ambiguous_destination|city_not_found/.test(
      body,
    )
  ) {
    throw new Error(`Trip planning failed in UI: ${body.slice(0, 400)}`)
  }
}

export function hotelPlannerUrl(h = RIXOS_BELEK) {
  const q = new URLSearchParams({
    hotelId: h.id,
    hotelName: h.name,
    city: h.city,
    country: h.country,
    lat: String(h.lat),
    lon: String(h.lon),
  })
  return `/oh-route?${q.toString()}`
}

export async function assertNoCriticalBrowserErrors(c: AuditCollectors) {
  const criticalConsole = c.consoleErrors.filter(
    (e) => !/Failed to load resource|net::ERR_|MapLibre|CORS|ResizeObserver/i.test(e),
  )
  const criticalNet = c.failedResponses.filter((r) => {
    // tile 404s / third-party noise
    if (/tile\.openstreetmap|a\.tile\.|b\.tile\.|c\.tile\./i.test(r)) return false
    if (/\/favicon/i.test(r)) return false
    // Allow identity search soft failures as PARTIAL
    if (/\/api\/visual-search/i.test(r) && /503|404|422/.test(r)) return false
    return / (4\d\d|5\d\d) /.test(` ${r}`) || /^(4|5)/.test(r)
  })
  expect(c.pageErrors, `pageerrors: ${c.pageErrors.join(' | ')}`).toEqual([])
  expect(criticalConsole, `console: ${criticalConsole.join(' | ')}`).toEqual([])
  // Soft-assert network: report but only fail hard on API 5xx to our backend
  const api5xx = criticalNet.filter((r) => /127\.0\.0\.1:8000|localhost:8000/.test(r) && /^5/.test(r))
  expect(api5xx, `api5xx: ${api5xx.join(' | ')}`).toEqual([])
}
