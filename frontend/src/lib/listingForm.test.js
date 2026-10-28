import { describe, expect, it } from 'vitest'
import {
  FROZEN_AFTER_BID,
  MAX_PHOTO_BYTES,
  changedFields,
  parseLocalInput,
  toLocalInputValue,
  toPatch,
  validateEdit,
  validateListing,
  validatePhotos,
  valuesFromListing,
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

describe('editing a listing', () => {
  const listing = {
    title: 'Hero cycle',
    category: 'cycle',
    condition: 'good',
    description: 'Barely used',
    starting_price: 500,
    min_increment: 50,
    closes_at: new Date(NOW + 5 * 3600 * 1000).toISOString(),
  }
  const initial = valuesFromListing(listing)

  it('fills the form from the listing', () => {
    expect(initial).toMatchObject({ title: 'Hero cycle', startingPrice: '500', minIncrement: '50', description: 'Barely used' })
    expect(parseLocalInput(initial.closesAt)).not.toBeNull()
  })
  it('reports nothing changed for an untouched form (even with stray spaces)', () => {
    expect(changedFields(initial, initial)).toEqual([])
    expect(changedFields(initial, { ...initial, title: '  Hero cycle ' })).toEqual([])
  })
  it('reports exactly the fields that changed', () => {
    expect(changedFields(initial, { ...initial, description: 'New', startingPrice: '600' })).toEqual(['description', 'startingPrice'])
  })
  it('builds a PATCH body with real numbers and an absolute closing time', () => {
    const values = { ...initial, startingPrice: '600', closesAt: inHours(48), title: ' New title ' }
    const body = toPatch(values, ['title', 'startingPrice', 'closesAt'])
    expect(body.title).toBe('New title')
    expect(body.starting_price).toBe(600)
    expect(typeof body.closes_at).toBe('string')
    expect(body.closes_at.endsWith('Z')).toBe(true)
    expect(Object.keys(body)).toEqual(['title', 'starting_price', 'closes_at'])
  })
  it('only validates what was changed', () => {
    // The closing time is only 5 minutes away now: not the seller's fault if they just fix a typo.
    const soon = { ...initial, closesAt: toLocalInputValue(new Date(NOW + 5 * 60 * 1000)), description: 'Fixed typo' }
    expect(validateEdit(soon, ['description'], NOW)).toEqual({})
    expect(validateEdit(soon, ['closesAt'], NOW).closesAt).toMatch(/at least 10 minutes/)
    expect(validateEdit({ ...initial, startingPrice: '0' }, ['startingPrice'], NOW).startingPrice).toBeTruthy()
  })
  it('freezes everything but the description once bidding has started', () => {
    expect(FROZEN_AFTER_BID).not.toContain('description')
    expect(FROZEN_AFTER_BID).toHaveLength(6)
  })
})

describe('handover spot', () => {
  const base = {
    title: 'Hero cycle', category: 'cycle', condition: 'good', description: '', startingPrice: '500',
    minIncrement: '50', closesAt: inHours(24), handoverSpot: '',
  }
  const listing = {
    title: 'Hero cycle', category: 'cycle', condition: 'good', description: '', starting_price: 500, min_increment: 50,
    closes_at: new Date(NOW + 5 * 3600 * 1000).toISOString(), handover_spot: 'Main Canteen',
  }

  it('is optional', () => {
    expect(validateListing(base, [png()], NOW).handoverSpot).toBeUndefined()
  })
  it('is limited to 120 characters', () => {
    expect(validateListing({ ...base, handoverSpot: 'x'.repeat(121) }, [png()], NOW).handoverSpot).toMatch(/120/)
    expect(validateListing({ ...base, handoverSpot: 'x'.repeat(120) }, [png()], NOW).handoverSpot).toBeUndefined()
  })
  it('fills the edit form from the listing, with nothing as an empty box', () => {
    expect(valuesFromListing(listing).handoverSpot).toBe('Main Canteen')
    expect(valuesFromListing({ ...listing, handover_spot: null }).handoverSpot).toBe('')
  })
  it('counts a changed spot but ignores stray spaces', () => {
    const initial = valuesFromListing(listing)
    expect(changedFields(initial, { ...initial, handoverSpot: 'Hostel Block A' })).toEqual(['handoverSpot'])
    expect(changedFields(initial, { ...initial, handoverSpot: '  Main Canteen ' })).toEqual([])
  })
  it('sends a cleared spot as null so the server stores nothing', () => {
    const initial = valuesFromListing(listing)
    expect(toPatch({ ...initial, handoverSpot: '   ' }, ['handoverSpot'])).toEqual({ handover_spot: null })
    expect(toPatch({ ...initial, handoverSpot: ' Library ' }, ['handoverSpot'])).toEqual({ handover_spot: 'Library' })
  })
})
