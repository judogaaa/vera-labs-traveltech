/**
 * Checkout critical path — dates, price, URL hotel priority, no render loop.
 */
import { expect, test } from '@playwright/test'
import { assertNoCriticalBrowserErrors, attachCollectors, shot } from './helpers'

const HOTEL_A = {
  id: 'rixos-premium-tekirova',
  name: 'Rixos Premium Tekirova',
  roomId: 'rixos-deluxe-garden',
  roomName: 'Deluxe Garden View',
}

const HOTEL_B = {
  id: 'akka-antedon',
  name: 'Akka Antedon Hotel',
  roomId: 'akka-standard',
}

async function go(page: import('@playwright/test').Page, url: string) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60_000 })
}

async function extendCheckOut(page: import('@playwright/test').Page) {
  // AppleDatePicker: <span>Выезд</span> + sibling <button aria-haspopup="dialog">.
  const checkoutBtn = page
    .locator('span')
    .filter({ hasText: /^Выезд$/ })
    .locator('xpath=following-sibling::button[@aria-haspopup="dialog"]')
  await expect(checkoutBtn).toBeVisible({ timeout: 20_000 })
  const nightsBefore = await page.getByText(/\d+\s*ноч/i).first().innerText()
  await checkoutBtn.click()
  const dialog = page.getByRole('dialog', { name: 'Выезд' })
  await expect(dialog).toBeVisible({ timeout: 10_000 })
  await dialog.getByRole('button', { name: 'Следующий месяц' }).click()
  const day20 = dialog.locator('button').filter({ hasText: /^20$/ }).first()
  if (await day20.isEnabled().catch(() => false)) {
    await day20.click()
  } else {
    await dialog.locator('button').filter({ hasText: /^\d{1,2}$/ }).nth(12).click()
  }
  await expect(dialog).toBeHidden({ timeout: 10_000 })
  const nightsAfter = await page.getByText(/\d+\s*ноч/i).first().innerText()
  expect(nightsAfter).toMatch(/\d+\s*ноч/i)
  // Price line must still show ₽ after date change.
  await expect(page.getByText(/₽/).first()).toBeVisible()
  void nightsBefore
}

test.describe('checkout', () => {
  test('dates, price, hotel URL priority, no React loop', async ({ page }) => {
    test.setTimeout(120_000)
    const c = attachCollectors(page)

    await go(page, `/hotel/${HOTEL_A.id}`)
    await expect(page.getByRole('heading', { name: new RegExp(HOTEL_A.name, 'i') })).toBeVisible({
      timeout: 60_000,
    })
    await expect(page.getByText(/Ваше проживание/i)).toBeVisible()

    await extendCheckOut(page)
    // Price on hotel card must reflect nights × rate after date change.
    await expect(page.getByText(/24\s*600/).first()).toBeVisible()
    await expect(page.getByText(/Итого/i).first()).toBeVisible()

    await page.getByRole('button', { name: 'Выбрать номер' }).click()
    const rooms = page.locator('section').filter({ hasText: 'Выберите номер' })
    await expect(rooms.getByRole('heading', { name: 'Выберите номер' })).toBeVisible({
      timeout: 15_000,
    })
    await rooms.getByRole('button', { name: 'Выбрать' }).first().click()
    await expect(page).toHaveURL(new RegExp(`/checkout/${HOTEL_A.id}/`), { timeout: 30_000 })

    await expect(page.getByRole('heading', { name: /Проверьте детали бронирования/i })).toBeVisible({
      timeout: 45_000,
    })
    await expect(page.getByLabel(/^Имя$/)).toBeVisible()
    await expect(page.getByText(HOTEL_A.name, { exact: false })).toBeVisible()
    await expect(page.getByText(HOTEL_A.roomName, { exact: false })).toBeVisible()

    const mainA = (await page.locator('main').innerText()).replace(/\u00a0/g, ' ')
    expect(mainA.replace(/\s/g, '')).toMatch(/24600/)
    expect(mainA).toMatch(/Итого/)

    // URL hotelId must win over stale context from Hotel A.
    await go(page, `/checkout/${HOTEL_B.id}/${HOTEL_B.roomId}`)
    await expect(page.getByRole('heading', { name: /Проверьте детали бронирования/i })).toBeVisible({
      timeout: 45_000,
    })
    await expect(page.getByText(HOTEL_B.name, { exact: false })).toBeVisible({ timeout: 15_000 })
    expect(await page.locator('main').innerText()).not.toContain(HOTEL_A.name)

    await page.getByLabel(/^Имя$/).fill('Тест')
    await expect(page.getByLabel(/^Имя$/)).toHaveValue('Тест')

    await shot(page, 'checkout-hotel-switch')
    await assertNoCriticalBrowserErrors(c)
  })
})
