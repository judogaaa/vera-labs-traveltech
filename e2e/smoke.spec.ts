/**
 * Stable frontend smoke — no live trip APIs required.
 * Used in CI; heavy live trip flows stay in core-flows.spec.ts.
 */
import { expect, test } from '@playwright/test'
import { RIXOS_BELEK, assertNoCriticalBrowserErrors, attachCollectors, shot } from './helpers'

const hotelCards = (page: import('@playwright/test').Page) =>
  page.locator('article[role="link"]')

async function go(page: import('@playwright/test').Page, url: string) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60_000 })
}

test.describe('smoke', () => {
  test('home loads', async ({ page }) => {
    test.setTimeout(90_000)
    const c = attachCollectors(page)
    await go(page, '/')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 60_000 })
    await expect(page.getByRole('button', { name: 'Загрузить фото', exact: true })).toBeVisible({
      timeout: 45_000,
    })
    await shot(page, 'smoke-home')
    await assertNoCriticalBrowserErrors(c)
  })

  test('O!Подбор addon loads without replacing visual search', async ({ page }) => {
    test.setTimeout(90_000)
    const c = attachCollectors(page)
    await go(page, '/hotel-intelligence')
    await expect(page.getByRole('heading', { name: 'О!Подбор', exact: true })).toBeVisible({ timeout: 45_000 })
    await expect(page.getByRole('button', { name: 'Найти', exact: true })).toBeDisabled()
    await page.locator('#hotel-intelligence-query').fill('Нужен тихий номер с плотными шторами')
    await expect(page.getByRole('button', { name: 'Найти', exact: true })).toBeEnabled()
    await expect(page.getByRole('link', { name: /Сравнить/i })).toBeVisible()
    if (process.env.E2E_REQUIRE_API === '1') {
      await expect(page.getByText('Hyatt Centric Levent Istanbul', { exact: false }).first()).toBeVisible()
    }
    await shot(page, 'hotel-intelligence-desktop')
    await page.setViewportSize({ width: 390, height: 844 })
    await shot(page, 'hotel-intelligence-mobile')
    await assertNoCriticalBrowserErrors(c)
  })

  test('catalog loads ≥10 cards', async ({ page }) => {
    test.setTimeout(180_000)
    const c = attachCollectors(page)
    await go(page, '/catalog')
    await expect(page.locator('main')).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('#catalog-grid [aria-busy="true"]')).toHaveCount(0, {
      timeout: 120_000,
    })
    const cards = hotelCards(page)
    await expect(cards.first()).toBeVisible({ timeout: 60_000 })
    await expect.poll(async () => cards.count(), { timeout: 60_000 }).toBeGreaterThanOrEqual(10)
    await shot(page, 'smoke-catalog')
    await assertNoCriticalBrowserErrors(c)
  })

  test('hotel detail opens', async ({ page }) => {
    test.setTimeout(90_000)
    const c = attachCollectors(page)
    await go(page, `/hotel/${RIXOS_BELEK.id}`)
    await expect(page.getByRole('heading', { name: /Rixos Premium Belek/i })).toBeVisible({
      timeout: 60_000,
    })
    await expect(page.getByRole('button', { name: /Спланировать поездку/i }).first()).toBeVisible()
    await shot(page, 'smoke-hotel')
    await assertNoCriticalBrowserErrors(c)
  })

  test('existing hotel detail links to additive O!Подбор with hotel context', async ({ page }) => {
    test.setTimeout(90_000)
    const c = attachCollectors(page)
    await go(page, `/hotel/${RIXOS_BELEK.id}`)
    await page.getByRole('button', { name: 'О!Подбор: особенности отеля' }).click()
    await expect(page).toHaveURL(/\/hotel-intelligence\?hotelId=/, { timeout: 30_000 })
    await expect(page.getByText('Rixos Premium Belek', { exact: true })).toBeVisible()
    await expect(page.getByText('Из каталога', { exact: true })).toBeVisible()
    await assertNoCriticalBrowserErrors(c)
  })

  test('/oh-route shell loads', async ({ page }) => {
    test.setTimeout(90_000)
    const c = attachCollectors(page)
    await go(page, '/oh-route')
    await expect(page.getByText(/О!Маршрут|AI-планировщик/i).first()).toBeVisible({
      timeout: 45_000,
    })
    await expect(page.locator('textarea').first()).toBeVisible()
    await shot(page, 'smoke-oh-route')
    await assertNoCriticalBrowserErrors(c)
  })
})
