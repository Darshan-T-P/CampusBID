import { describe, expect, it } from 'vitest'
import {
  MAX_PHOTO_BYTES,
  parseLocalInput,
  toLocalInputValue,
  validateListing,
  validatePhotos,
} from './listingForm'

const NOW = Date.parse('2026-05-01T12:00:00Z')
const png = (name = 'a.png', size = 1000) => ({ name, size, type: 'image/png' })
const inHours = (h) => toLocalInputValue(new Date(NOW + h * 3600 * 1000))
const good = () => ({
  title: 'Hero cycle',
  category: 'cycle',
  condition: 'good',
  description: 'Barely used',
  startingPrice: '500',
  minIncrement: '50',
  closesAt: inHours(24),
})

describe('datetime-local helpers', () => {
  it('round-trips through the input format', () => {
    const date = new Date(2026, 4, 1, 9, 5) // local time
    expect(toLocalInputValue(date)).toBe('2026-05-01T09:05')
    expect(parseLocalInput('2026-05-01T09:05').getTime()).toBe(date.getTime())
  })
  it('rejects junk', () => {
    for (const bad of ['', 'tomorrow', '2026-13-45T99:99', '2026-05-01']) expect(parseLocalInput(bad)).toBeNull()
  })
})

describe('validatePhotos', () => {
  it('needs 1 to 5 photos', () => {
    expect(validatePhotos([])).toMatch(/at least one/)
    expect(validatePhotos(Array.from({ length: 6 }, (_, i) => png(`${i}.png`)))).toMatch(/at most 5/)
    expect(validatePhotos([png()])).toBeNull()
    expect(validatePhotos(Array.from({ length: 5 }, (_, i) => png(`${i}.png`)))).toBeNull()
  })
  it('names the offending file when the type or size is wrong', () => {
    expect(validatePhotos([{ name: 'notes.pdf', size: 10, type: 'application/pdf' }])).toMatch(/notes.pdf.*JPEG, PNG or WebP/)
    expect(validatePhotos([png('big.png', MAX_PHOTO_BYTES + 1)])).toMatch(/big.png.*5 MB/)
    expect(validatePhotos([png('ok.png', MAX_PHOTO_BYTES)])).toBeNull()
  })
})

describe('validateListing', () => {
  it('accepts a complete, sensible form', () => {
    expect(validateListing(good(), [png()], NOW)).toEqual({})
  })
  it('flags every missing field at once', () => {
    const blank = { title: '', category: '', condition: '', description: '', startingPrice: '', minIncrement: '', closesAt: '' }
    expect(Object.keys(validateListing(blank, [], NOW)).sort()).toEqual(
      ['category', 'closesAt', 'condition', 'minIncrement', 'photos', 'startingPrice', 'title'],
    )
  })
  it('treats a blank-looking title as missing', () => {
    expect(validateListing({ ...good(), title: '   ' }, [png()], NOW).title).toBeTruthy()
  })
  it('wants whole, positive, bounded prices', () => {
    for (const bad of ['0', '-5', '12.5', 'abc', '10000001']) {
      expect(validateListing({ ...good(), startingPrice: bad }, [png()], NOW).startingPrice, bad).toBeTruthy()
      expect(validateListing({ ...good(), minIncrement: bad }, [png()], NOW).minIncrement, bad).toBeTruthy()
    }
    expect(validateListing({ ...good(), startingPrice: '10000000' }, [png()], NOW).startingPrice).toBeUndefined()
  })
  it('enforces the 10 minute to 30 day window against the server clock', () => {
    const errAt = (hours) => validateListing({ ...good(), closesAt: inHours(hours) }, [png()], NOW).closesAt
    expect(errAt(-1)).toMatch(/at least 10 minutes/)
    expect(errAt(0.1)).toMatch(/at least 10 minutes/) // 6 minutes
    expect(errAt(0.25)).toBeUndefined() // 15 minutes
    expect(errAt(24 * 30 + 1)).toMatch(/at most 30 days/)
    expect(errAt(24 * 29)).toBeUndefined()
  })
  it('rejects a closing time that is not a real date', () => {
    expect(validateListing({ ...good(), closesAt: 'soon' }, [png()], NOW).closesAt).toMatch(/valid/)
  })
})
