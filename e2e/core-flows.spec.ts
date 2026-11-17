import { expect, test } from '@playwright/test'
import path from 'node:path'
import {
  HOTEL_CTX_MSG,
  ISTANBUL_SIX_WISHES_MSG,
  KAZAN_MSG,
  RIXOS_BELEK,
  assertNoCriticalBrowserErrors,
  attachCollectors,
  hotelPlannerUrl,
  sendTripMessage,
  shot,
  waitForTripReady,
} from './helpers'

const hotelCards = (page: import('@playwright/test').Page) =>
  page.locator('article[role="link"]')

async function go(page: import('@playwright/test').Page, url: string) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60_000 })
}

test('1. Home loads', async ({ page }) => {
  test.setTimeout(120_000)
  const c = attachCollectors(page)
  await go(page, '/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole('button', { name: 'Загрузить фото', exact: true })).toBeVisible({
    timeout: 60_000,
  })
  await shot(page, '01-home-1440')
  await assertNoCriticalBrowserErrors(c)
})

test('2. Catalog loads (≥10 cards)', async ({ page }) => {
  test.setTimeout(180_000)
  const c = attachCollectors(page)
  await go(page, '/catalog')
  await expect(page.locator('main')).toBeVisible({ timeout: 60_000 })
  // Curated catalog is fetched async from /data/curatedHotelsSlim.json — wait
  // until the grid leaves the loading state and has a real page of cards.
  await expect(page.locator('#catalog-grid [aria-busy="true"]')).toHaveCount(0, {
    timeout: 120_000,
  })
  const cards = hotelCards(page)
  await expect(cards.first()).toBeVisible({ timeout: 60_000 })
  await expect.poll(async () => cards.count(), { timeout: 60_000 }).toBeGreaterThanOrEqual(10)
  await shot(page, '02-catalog')
  await assertNoCriticalBrowserErrors(c)
})

test('3. Hotel detail opens', async ({ page }) => {
  test.setTimeout(120_000)
  const c = attachCollectors(page)
  await go(page, `/hotel/${RIXOS_BELEK.id}`)
  await expect(page.getByRole('heading', { name: /Rixos Premium Belek/i })).toBeVisible({
    timeout: 60_000,
  })
  await expect(page.getByRole('button', { name: /Спланировать поездку/i }).first()).toBeVisible()
  await shot(page, '03-hotel-detail')
  await assertNoCriticalBrowserErrors(c)
})

test('4. Hotel → planner navigation with context', async ({ page }) => {
  test.setTimeout(120_000)
  const c = attachCollectors(page)
  await go(page, `/hotel/${RIXOS_BELEK.id}`)
  await page.getByRole('button', { name: /Спланировать поездку/i }).first().click()
  await expect(page).toHaveURL(/\/oh-route\?/, { timeout: 30_000 })
  expect(page.url()).toContain('hotelId=')
  expect(page.url()).toMatch(/lat=|lon=/)
  await expect(page.getByText(/Rixos Premium Belek/i).first()).toBeVisible({ timeout: 30_000 })
  await shot(page, '04-hotel-to-planner')
  await assertNoCriticalBrowserErrors(c)
})

test('5. /oh-route loads', async ({ page }) => {
  test.setTimeout(90_000)
  const c = attachCollectors(page)
  await go(page, '/oh-route')
  await expect(page.getByText(/О!Маршрут|AI-планировщик/i).first()).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('textarea').first()).toBeVisible()
  await shot(page, '05-oh-route-empty')
  await assertNoCriticalBrowserErrors(c)
})

test('6–9. Kazan trip + map/trip toggle + edit + PDF', async ({ page }) => {
  test.setTimeout(360_000)
  const c = attachCollectors(page)
  await go(page, '/oh-route')
  await sendTripMessage(page, KAZAN_MSG)
  await waitForTripReady(page)
  await expect(page.locator('.maplibregl-canvas, canvas').first()).toBeVisible({ timeout: 30_000 })
  await shot(page, '06-desktop-route-kazan')

  await page.getByRole('button', { name: 'Поездка' }).first().click()
  await expect(page.getByText(/План поездки|День 1/i).first()).toBeVisible()
  await shot(page, '07-trip-view')

  await page.getByRole('button', { name: 'Карта' }).first().click()
  await expect(page.locator('.maplibregl-canvas, canvas').first()).toBeVisible()
  await shot(page, '09-map-toggle')

  await sendTripMessage(page, 'Убери музей')
  await waitForTripReady(page)
  await page.getByRole('button', { name: 'Поездка' }).first().click()
  await expect(page.getByText(/День 1|План поездки/i).first()).toBeVisible()
  await shot(page, '08-edit-remove-museum')

  const pdfLink = page.locator('a[href*="/api/trips/"][href*="/pdf"]').first()
  await expect(pdfLink).toBeVisible({ timeout: 15_000 })
  const href = await pdfLink.getAttribute('href')
  expect(href).toBeTruthy()
  const res = await page.request.get(href!)
  expect(res.status()).toBe(200)
  expect(res.headers()['content-type'] || '').toMatch(/pdf/i)
  const buf = await res.body()
  expect(buf.byteLength).toBeGreaterThan(500)
  expect(buf.subarray(0, 4).toString()).toBe('%PDF')
  await shot(page, '10-pdf-ready')
  await assertNoCriticalBrowserErrors(c)
})

test('10. Mobile /oh-route (390x844)', async ({ page }) => {
  test.setTimeout(240_000)
  const c = attachCollectors(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await go(page, '/oh-route')
  await expect(page.locator('textarea').first()).toBeVisible()
  await sendTripMessage(page, 'Казань на 1 день, главные достопримечательности')
  await waitForTripReady(page)
  await page.getByRole('button', { name: 'Карта' }).first().click()
  await expect(page.locator('.maplibregl-canvas, canvas').first()).toBeVisible()
  await shot(page, '11-mobile-route')
  await page.getByRole('button', { name: 'Поездка' }).first().click()
  await expect(page.getByText(/План поездки|День 1/i).first()).toBeVisible()
  await page.getByRole('button', { name: 'Чат' }).first().click()
  await expect(page.locator('textarea').first()).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 8,
  )
  expect(overflow).toBeFalsy()
  await assertNoCriticalBrowserErrors(c)
})

test('Hotel-context route + further edits', async ({ page }) => {
  test.setTimeout(360_000)
  const c = attachCollectors(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await go(page, hotelPlannerUrl())
  await expect(page.getByText(/Rixos Premium Belek/i).first()).toBeVisible()
  await sendTripMessage(page, HOTEL_CTX_MSG)
  await waitForTripReady(page)
  await shot(page, '12-hotel-context-route')
  await sendTripMessage(page, 'Добавь пляж после обеда')
  await waitForTripReady(page)
  await shot(page, '13-edit-add-beach')
  await sendTripMessage(page, 'Слишком много ходить')
  await waitForTripReady(page)
  await shot(page, '14-edit-less-walking')
  await assertNoCriticalBrowserErrors(c)
})

test('Responsive viewports smoke', async ({ page }) => {
  test.setTimeout(180_000)
  const viewports = [
    { w: 1440, h: 900, name: '1440x900' },
    { w: 1280, h: 800, name: '1280x800' },
    { w: 768, h: 1024, name: '768x1024' },
    { w: 390, h: 844, name: '390x844' },
  ]
  for (const v of viewports) {
    await page.setViewportSize({ width: v.w, height: v.h })
    await go(page, '/oh-route')
    await expect(page.locator('textarea').first()).toBeVisible({ timeout: 30_000 })
    await shot(page, `viewport-oh-route-${v.name}`)
    await go(page, '/catalog')
    await expect(hotelCards(page).first()).toBeVisible({ timeout: 60_000 })
    await shot(page, `viewport-catalog-${v.name}`)
  }
})

test('Istanbul: 6 wishes, morning start, map, replace bar', async ({ page }) => {
  test.setTimeout(420_000)
  const c = attachCollectors(page)
  const api = process.env.E2E_API_URL || 'http://127.0.0.1:8000'
  await go(page, '/oh-route')

  await sendTripMessage(page, ISTANBUL_SIX_WISHES_MSG)

  // Progress must advance past the optimistic first step while the request is live.
  await expect
    .poll(
      async () => {
        const body = await page.locator('body').innerText()
        if (/Ищу места|Проверяю расстояния|Собираю маршрут/.test(body)) return 'advanced'
        if (/Маршрут по|День 1|План поездки/.test(body)) return 'done'
        if (/Не удалось построить маршрут/.test(body)) return 'failed'
        return 'waiting'
      },
      { timeout: 120_000 },
    )
    .toMatch(/advanced|done/)

  await waitForTripReady(page, 300_000)
  await expect(page.locator('.maplibregl-canvas, canvas').first()).toBeVisible({ timeout: 30_000 })
  await shot(page, '20-istanbul-map')

  await page.getByRole('button', { name: 'Поездка' }).first().click()
  await expect(page.getByText(/День 1|План поездки/i).first()).toBeVisible()
  const tripBody = await page.locator('body').innerText()
  // First stop must be morning (explicit 10:00), not an evening-only day start.
  expect(tripBody).toMatch(/10:\d{2}/)

  const pdfLink = page.locator('a[href*="/api/trips/"][href*="/pdf"]').first()
  await expect(pdfLink).toBeVisible({ timeout: 15_000 })
  const href = await pdfLink.getAttribute('href')
  expect(href).toBeTruthy()
  const tripId = href!.match(/\/api\/trips\/([^/]+)\/pdf/)?.[1]
  expect(tripId).toBeTruthy()
  const tripRes = await page.request.get(`${api}/api/trips/${tripId}`)
  expect(tripRes.status()).toBe(200)
  const trip = (await tripRes.json()).trip
  expect(trip.intent.startTime).toBe('10:00')
  expect(trip.intent.wishSequence.length).toBeGreaterThanOrEqual(6)
  const cats = new Set(
    trip.days.flatMap((d: { stops: { category: string }[] }) => d.stops.map((s) => s.category)),
  )
  for (const needed of ['attraction', 'museum', 'viewpoint', 'restaurant', 'cafe', 'bar']) {
    expect(cats.has(needed), `missing category ${needed} in ${[...cats]}`).toBeTruthy()
  }
  const firstStart = trip.days[0].stops[0].startTime as string
  expect(firstStart < '14:00').toBeTruthy()
  const segs = trip.days[0].segments as { mode: string; distanceMeters: number }[]
  for (const s of segs) {
    if (s.mode === 'walk') expect(s.distanceMeters).toBeLessThanOrEqual(4500)
  }
  await shot(page, '21-istanbul-trip')

  await page.getByRole('button', { name: 'Чат' }).first().click().catch(() => {})
  await sendTripMessage(page, 'Замените бар на винный бар')
  await waitForTripReady(page, 180_000)
  await page.getByRole('button', { name: 'Поездка' }).first().click()
  const after = await page.locator('body').innerText()
  expect(after).toMatch(/Заменил|винн|бар/i)
  await shot(page, '22-istanbul-replace-bar')

  const tripAfterReplace = (await (await page.request.get(`${api}/api/trips/${tripId}`)).json()).trip
  const stopsBefore = tripAfterReplace.days[0].stops.length as number
  const idsBefore = tripAfterReplace.days[0].stops.map((s: { placeId: string }) => s.placeId)
  await sendTripMessage(page, 'Оставь маршрут без изменений')
  await waitForTripReady(page, 120_000)
  const trip2 = (await (await page.request.get(`${api}/api/trips/${tripId}`)).json()).trip
  expect(trip2.days[0].stops.length).toBe(stopsBefore)
  expect(trip2.days[0].stops.map((s: { placeId: string }) => s.placeId)).toEqual(idsBefore)
  await assertNoCriticalBrowserErrors(c)
})

test('Visual search full-image (technical; identity may be PARTIAL)', async ({ page }) => {
  test.setTimeout(180_000)
  const c = attachCollectors(page)
  await go(page, '/')
  await expect(page.locator('input[type="file"]').first()).toBeAttached({ timeout: 60_000 })
  const demo = path.resolve('public/demo/hotels/rixos/01.jpg')
  await page.locator('input[type="file"]').first().setInputFiles(demo)
  await expect(page).toHaveURL(/\/search\/preview/, { timeout: 20_000 })
  await shot(page, '15-search-preview')
  await page.getByRole('button', { name: /Искать весь отель/i }).first().click()
  await page.waitForURL(/\/search\/(analyzing|result|matches|no-match)/, { timeout: 60_000 })
  await page.waitForURL(/\/search\/(result|matches|no-match)/, { timeout: 120_000 })
  await shot(page, '16-search-result')
  await expect(page.locator('main').first()).toBeVisible()
  await assertNoCriticalBrowserErrors(c)
})
