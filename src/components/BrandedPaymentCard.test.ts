import { describe, expect, it } from 'vitest'
import { maskCardNumber, maskCvcDisplay } from './BrandedPaymentCard'

describe('BrandedPaymentCard mask', () => {
  it('masks incomplete numbers', () => {
    expect(maskCardNumber('4111')).toContain('•')
    expect(maskCardNumber('')).toBe('•••• •••• •••• ••••')
  })

  it('reveals only the last digits when enough are entered', () => {
    const masked = maskCardNumber('4111111111111234')
    expect(masked.endsWith('1234')).toBe(true)
    expect(masked.startsWith('••••')).toBe(true)
    expect(masked.includes('4111')).toBe(false)
  })

  it('never includes a CVC field in the mask output', () => {
    expect(maskCardNumber('4111111111111234')).not.toMatch(/cvc/i)
  })
})

describe('BrandedPaymentCard CVC display', () => {
  it('never reveals real CVC digits', () => {
    expect(maskCvcDisplay('123')).toBe('•••')
    expect(maskCvcDisplay('9876')).toBe('••••')
    expect(maskCvcDisplay('123')).not.toMatch(/\d/)
  })

  it('shows placeholder bullets when empty', () => {
    expect(maskCvcDisplay('')).toBe('•••')
  })
})
