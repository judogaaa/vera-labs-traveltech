/**
 * О!Подбор E2E
 * - Offline smoke: UI shell survives without API (honest error, no crash).
 * - Live integration: API on :8000 REQUIRED — absence is FAIL (not skip).
 *
 * Prefer an isolated SQLite copy:
 *   python scripts/e2e_hi_isolated_db.py
 *   $env:HOTEL_INTELLIGENCE_DB = "artifacts/e2e/hi_isolated/intelligence.sqlite"
 *   npm run dev:api
 */
import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const API = process.env.E2E_API_URL || 'http://127.0.0.1:8000'
const WRITE_TOKEN =
  process.env.E2E_HI_WRITE_TOKEN ||
  process.env.VITE_HI_WRITE_TOKEN ||
  process.env.HOTEL_INTELLIGENCE_WRITE_TOKEN ||
  'vera-labs-local-demo-write'
const WRITE = { 'X-Write-Token': WRITE_TOKEN, 'X-Demo-Mutation': '1' }

async function requireApi(): Promise<void> {
  let last = ''
  try {
    const r = await fetch(`${API}/api/hotel-intelligence/status`)
    last = `HTTP ${r.status}`
    if (!r.ok) throw new Error(last)
    const j = (await r.json()) as { hotels?: number; ok?: boolean }
    if (!j.ok || (j.hotels ?? 0) < 1) {
      throw new Error(`status ok=${j.ok} hotels=${j.hotels}`)
    }
  } catch (e) {
    throw new Error(
      `Live E2E requires hotel-intelligence API at ${API} with demo hotels loaded (${e}). ` +
        `Do not skip — start API (preferably with isolated DB via scripts/e2e_hi_isolated_db.py).`,
    )
  }
}

test.describe('О!Подбор offline smoke', () => {
  test('shell loads and shows honest error when API down', async ({ page }) => {
    test.setTimeout(60_000)
    await page.route('**/api/hotel-intelligence/**', (route) =>
      route.fulfill({ status: 503, body: JSON.stringify({ detail: 'offline' }) }),
    )
    await page.goto('/hotel-intelligence')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await page
      .getByRole('button', { name: /Тихий номер|метро|пример/i })
      .first()
      .click()
      .catch(async () => {
        await page.locator('#hotel-intelligence-query').fill('тихий отель рядом с метро')
        await page.getByRole('button', { name: /Найти|Искать|Отправить/i }).click()
      })
    await expect(page.locator('body')).not.toContainText(/Internal Server Error/i)
  })

  test('hotelier and compare shells load', async ({ page }) => {
    await page.goto('/hotel-intelligence/hotelier')
    await expect(page.locator('body')).toBeVisible()
    await page.goto('/hotel-intelligence/compare')
    await expect(page.locator('body')).toBeVisible()
  })
})

test.describe('О!Подбор live integration', () => {
  test.beforeAll(async () => {
    await requireApi()
  })

  test('search returns hotels with walk evidence', async ({ page, request }) => {
    test.setTimeout(120_000)
    const search = await request.post(`${API}/api/hotel-intelligence/search`, {
      data: { query: 'максимум 10 минут пешком до метро', limit: 5 },
    })
    expect(search.status()).toBe(200)
    const body = await search.json()
    expect(body.results?.length).toBeGreaterThan(0)
    const top = body.results[0]
    expect(
      top.matched?.some((m: { attribute_key: string }) => m.attribute_key === 'walk_to_metro'),
    ).toBeTruthy()

    await page.goto('/hotel-intelligence')
    await page.locator('#hotel-intelligence-query').fill('максимум 10 минут пешком до метро')
    await page.getByRole('button', { name: /Найти|Искать|Отправить/i }).click()
    await expect(page.getByText(top.name || top.hotel_id).first()).toBeVisible({
      timeout: 30_000,
    })
  })

  test('map renders canvas tiles and markers after search', async ({ page }) => {
    test.setTimeout(120_000)
    const tileHits: string[] = []
    page.on('response', (res) => {
      const u = res.url()
      if (
        /tile\.openstreetmap|basemaps\.cartocdn\.com|tiles\.openfreemap|maps\.wikimedia/.test(u) &&
        res.status() < 400
      ) {
        tileHits.push(u)
      }
    })

    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/hotel-intelligence')
    const queryBox = page.locator('#hotel-intelligence-query')
    await expect(queryBox).toBeVisible({ timeout: 45_000 })
    await queryBox.fill('максимум 10 минут пешком до метро')
    await page.getByRole('button', { name: /Найти|Искать|Отправить/i }).click()
    await expect(page.getByText(/\d+\s+вариантов/i).first()).toBeVisible({ timeout: 60_000 })

    const map = page.getByTestId('hi-map')
    await expect(map).toBeVisible({ timeout: 30_000 })

    // Map host with non-zero size (DOM raster tiles — not an empty grey shell).
    await page.waitForFunction(
      () => {
        const host = document.querySelector(
          '[data-testid="hi-map-canvas-host"], [data-testid="hi-map"]',
        ) as HTMLElement | null
        if (!host) return false
        const r = host.getBoundingClientRect()
        const imgs = host.querySelectorAll('img').length
        return r.width > 120 && r.height > 120 && imgs >= 1
      },
      { timeout: 45_000 },
    )

    await page.waitForFunction(
      () => {
        const el = document.querySelector('[data-testid="hi-map"]')
        if (!el) return false
        const status = el.getAttribute('data-map-status')
        const tiles = el.getAttribute('data-map-tiles')
        const markers = document.querySelectorAll(
          '[data-testid="hi-map"] .hi-map-marker, [data-testid="hi-map"] [data-hi-marker]',
        ).length
        const tileImgs = el.querySelectorAll('[data-testid="hi-map-canvas-host"] img').length
        const err = Boolean(document.querySelector('[data-testid="hi-map-tile-error"]'))
        // Pass if tiles loaded + markers, OR honest tile error with markers still present.
        return (
          markers >= 1 &&
          tileImgs >= 1 &&
          ((status === 'ready' && tiles === 'loaded') || err || (tiles === 'loaded' && markers >= 1))
        )
      },
      { timeout: 60_000 },
    )

    const markerCount = await page.locator('[data-testid="hi-map"] [data-hi-marker]').count()
    const status = await map.getAttribute('data-map-status')
    const tiles = await map.getAttribute('data-map-tiles')
    const hasErr = await page.getByTestId('hi-map-tile-error').count()
    expect(markerCount).toBeGreaterThan(0)
    expect(status === 'ready' || status === 'error' || hasErr > 0).toBeTruthy()
    // Prefer real tiles; allow explicit error banner as honest fallback.
    expect(tiles === 'loaded' || tileHits.length > 0 || hasErr > 0).toBeTruthy()

    const out = path.resolve('artifacts/e2e/screenshots/hi-accept')
    fs.mkdirSync(out, { recursive: true })
    await page.screenshot({
      path: path.join(out, 'hotel-intelligence_search_1440x900.png'),
      fullPage: false,
    })
  })

  test('city filter does not return Istanbul for Kazan query', async ({ request }) => {
    const search = await request.post(`${API}/api/hotel-intelligence/search`, {
      data: { query: 'тихий отель в Казани', limit: 10 },
    })
    expect(search.status()).toBe(200)
    const body = await search.json()
    expect(body.city_filter_applied).toBeTruthy()
    expect(body.results || []).toEqual([])
    expect(body.note).toBe('no_hotels_in_requested_city')
  })

  test('full path: search → hotelier answer → re-search → conflict', async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000)
    const hotels = await (await request.get(`${API}/api/hotel-intelligence/hotels`)).json()
    const hotel =
      hotels.hotels?.find((h: { name?: string }) => /Amber/i.test(h.name || '')) ||
      hotels.hotels?.[1] ||
      hotels.hotels?.[0]
    expect(hotel?.hotel_id).toBeTruthy()

    // Detail / evidence
    await page.goto(`/hotel-intelligence/hotel/${hotel.hotel_id}`)
    await expect(page.locator('body')).toContainText(
      /метро|доказател|атрибут|источник|walk/i,
    )

    // Compare shell
    await page.goto('/hotel-intelligence/compare')
    await expect(page.locator('body')).toBeVisible()

    // Ensure open question
    let qs = await (
      await request.get(
        `${API}/api/hotel-intelligence/hotelier/questions?hotel_id=${hotel.hotel_id}&status=open`,
      )
    ).json()
    let q = (qs.questions || []).find(
      (x: { attribute_key: string }) => x.attribute_key === 'blackout_curtains',
    )
    if (!q) {
      const enrich = await request.post(`${API}/api/hotel-intelligence/enrich`, {
        headers: WRITE,
        data: { hotel_id: hotel.hotel_id, attributes: ['blackout_curtains'] },
      })
      expect([200, 429]).toContain(enrich.status())
      qs = await (
        await request.get(
          `${API}/api/hotel-intelligence/hotelier/questions?hotel_id=${hotel.hotel_id}&status=open`,
        )
      ).json()
      q = (qs.questions || []).find(
        (x: { attribute_key: string }) => x.attribute_key === 'blackout_curtains',
      )
    }
    expect(q?.question_id).toBeTruthy()

    const ans1 = await request.post(
      `${API}/api/hotel-intelligence/hotelier/questions/${q.question_id}/answer`,
      {
        headers: WRITE,
        data: {
          raw_text: 'В Deluxe установлены плотные шторы блэкаут. В Standard — обычные.',
          simulated: true,
        },
      },
    )
    expect(ans1.status()).toBe(200)
    const extracted = await ans1.json()
    expect(extracted.observations?.length).toBeGreaterThan(0)
    expect(
      extracted.observations.every(
        (o: { status: string; sources?: { kind: string }[] }) =>
          o.status !== 'verified' &&
          (o.sources || []).some((s) => s.kind === 'hotelier_simulated'),
      ),
    ).toBeTruthy()

    const search = await request.post(`${API}/api/hotel-intelligence/search`, {
      data: { query: 'Deluxe с плотными шторами', limit: 10 },
    })
    expect(search.status()).toBe(200)
    const body = await search.json()
    const hit = body.results?.find((r: { hotel_id: string }) => r.hotel_id === hotel.hotel_id)
    expect(hit).toBeTruthy()
    const matched = hit.matched?.find(
      (m: { attribute_key: string }) => m.attribute_key === 'blackout_curtains',
    )
    if (matched) {
      const scopeBlob = JSON.stringify(matched).toLowerCase()
      expect(scopeBlob).toMatch(/deluxe|room_type|room/)
      expect(matched.hotel_wide).not.toBe(true)
      expect(matched.status).not.toBe('verified')
    }

    // Contradiction → conflict (trace and/or conflicts API)
    const ans2 = await request.post(
      `${API}/api/hotel-intelligence/hotelier/questions/${q.question_id}/answer`,
      {
        headers: WRITE,
        data: {
          raw_text: 'Извините, в Deluxe blackout нет — ошибка.',
          simulated: true,
        },
      },
    )
    expect(ans2.status()).toBe(200)
    const ans2body = await ans2.json()
    const conflictInTrace = JSON.stringify(ans2body.trace || {}).includes('conflict')

    const conflicts = await (
      await request.get(`${API}/api/hotel-intelligence/conflicts?hotel_id=${hotel.hotel_id}`)
    ).json()
    expect(conflictInTrace || (conflicts.conflicts || []).length > 0).toBeTruthy()

    // Persistence across new status read (API process keeps store)
    const again = await (await request.get(`${API}/api/hotel-intelligence/status`)).json()
    expect(again.ok).toBeTruthy()

    // Hotelier UI
    await page.goto('/hotel-intelligence/hotelier')
    await expect(page.locator('body')).toContainText(/симуляц|отельер|вопрос/i)
  })

  test('write without auth forbidden; demo header alone insufficient', async ({ request }) => {
    const bare = await request.post(`${API}/api/hotel-intelligence/bootstrap`)
    expect([401, 403]).toContain(bare.status())

    const demoOnly = await request.post(`${API}/api/hotel-intelligence/enrich`, {
      headers: { 'X-Demo-Mutation': '1' },
      data: { hotel_id: 'oh-curated-000002' },
    })
    expect([401, 403]).toContain(demoOnly.status())

    const qs = await (await request.get(`${API}/api/hotel-intelligence/hotelier/questions`)).json()
    const qid = qs.questions?.[0]?.question_id
    expect(qid).toBeTruthy()
    const ans = await request.post(
      `${API}/api/hotel-intelligence/hotelier/questions/${qid}/answer`,
      { data: { raw_text: 'fake official', simulated: false } },
    )
    expect([401, 403]).toContain(ans.status())
  })

  test('hotel detail page shows evidence', async ({ page, request }) => {
    const hotels = await (await request.get(`${API}/api/hotel-intelligence/hotels`)).json()
    const id = hotels.hotels?.[0]?.hotel_id
    expect(id).toBeTruthy()
    await page.goto(`/hotel-intelligence/hotel/${id}`)
    await expect(page.locator('body')).toContainText(
      /метро|walk|доказател|атрибут|evidence|источник/i,
    )
  })
})

test.describe('Visual contact sheet', () => {
  test('captures desktop tablet mobile shots when API up', async ({ browser }) => {
    test.setTimeout(180_000)
    await requireApi()
    const outDir = path.resolve('artifacts/e2e/screenshots/hi-final')
    fs.mkdirSync(outDir, { recursive: true })
    const viewports = [
      { name: '1440x900', width: 1440, height: 900 },
      { name: '768x1024', width: 768, height: 1024 },
      { name: '390x844', width: 390, height: 844 },
    ]
    const routes = [
      '/hotel-intelligence',
      '/hotel-intelligence/hotelier',
      '/hotel-intelligence/compare',
    ]
    const sheet: { file: string; route: string; viewport: string }[] = []
    for (const vp of viewports) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
      })
      const page = await context.newPage()
      for (const route of routes) {
        await page.goto(`http://127.0.0.1:5173${route}`, {
          waitUntil: 'networkidle',
          timeout: 60_000,
        })
        await page.waitForTimeout(1000)
        const file = path.join(
          outDir,
          `${route.replace(/\//g, '_').replace(/^_/, '') || 'root'}_${vp.name}.png`,
        )
        await page.screenshot({ path: file, fullPage: true })
        sheet.push({ file, route, viewport: vp.name })
      }
      await context.close()
    }
    fs.writeFileSync(
      path.join(outDir, 'CONTACT_SHEET.md'),
      [
        '# О!Подбор visual contact sheet',
        '',
        ...sheet.map((s) => `- \`${s.viewport}\` ${s.route} → \`${path.basename(s.file)}\``),
        '',
      ].join('\n'),
      'utf8',
    )
    expect(sheet.length).toBeGreaterThanOrEqual(9)
  })
})
