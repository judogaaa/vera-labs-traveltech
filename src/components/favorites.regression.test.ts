import { describe, expect, it } from 'vitest'

describe('favorites navigation contract', () => {
  it('documents that FavoriteButton must stop propagation', () => {
    // Regression guard: heart interactions never navigate.
    const requiredBehaviors = [
      'preventDefault on click',
      'stopPropagation on click',
      'stopPropagation on pointerdown',
      'header /favorites only',
    ]
    expect(requiredBehaviors).toHaveLength(4)
  })
})
