import { describe, expect, it } from 'vitest'
import { hammingDistance } from './imageFingerprint'

describe('image fingerprint helpers', () => {
  it('hammingDistance is zero for identical hashes', () => {
    expect(hammingDistance(0b1010n, 0b1010n)).toBe(0)
  })

  it('hammingDistance counts differing bits', () => {
    expect(hammingDistance(0b1111n, 0b0000n)).toBe(4)
    expect(hammingDistance(0b1000n, 0b0001n)).toBe(2)
  })

  it('exact threshold stays strict for near hashes', () => {
    const exactMax = 8
    expect(hammingDistance(0n, (1n << 5n) - 1n)).toBeLessThanOrEqual(exactMax)
    expect(hammingDistance(0n, (1n << 12n) - 1n)).toBeGreaterThan(exactMax)
  })
})
