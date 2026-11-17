import { describe, expect, it } from 'vitest'
import { previewRequestedAttributes } from './intentPreview'

describe('hotel intelligence: honest local intent preview', () => {
  it('finds multiple explicit hotel wishes without claiming results', () => {
    const found = previewRequestedAttributes(
      'Нужен тихий номер с видом на закат и плотными шторами, 10 минут пешком до метро',
    )
    expect(found.map(({ key }) => key)).toEqual(['quiet', 'sunset', 'walkability', 'blackout'])
    expect(found.every(({ plannedSource, limitation }) => plannedSource && limitation)).toBe(true)
  })

  it('does not fabricate attributes for an unknown request', () => {
    expect(previewRequestedAttributes('Мне нужен отель с морским настроением')).toEqual([])
    expect(previewRequestedAttributes('   ')).toEqual([])
  })

  it('recognizes family, pets and night access', () => {
    const found = previewRequestedAttributes('С детьми, собакой, рядом круглосуточная аптека')
    expect(found.map((item) => item.key)).toEqual(['night-services', 'family', 'pets'])
  })
})
