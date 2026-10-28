import { describe, expect, it } from 'vitest'
import {
  DEFAULT_FILTERS,
  apiQuery,
  filtersFromParams,
  filtersToParams,
  hasActiveFilters,
  isPriceRangeInvalid,
} from './query'

const parse = (qs) => filtersFromParams(new URLSearchParams(qs))

describe('filtersFromParams', () => {
  it('uses defaults for an empty URL', () => {
    expect(parse('')).toEqual(DEFAULT_FILTERS)
  })
  it('reads every filter', () => {
    expect(parse('q=hero+cycle&category=cycle&condition=good&min_price=100&max_price=900&closing_soon=1&sort=newest&page=3')).toEqual({
      q: 'hero cycle',
      category: 'cycle',
      condition: 'good',
      minPrice: '100',
      maxPrice: '900',
      closingSoon: true,
      sort: 'newest',
      page: 3,
    })
  })
  it('falls back to page 1 for junk page numbers', () => {
    for (const bad of ['0', '-2', 'abc', '']) expect(parse(`page=${bad}`).page).toBe(1)
  })
})

describe('filtersToParams', () => {
  it('omits defaults so URLs stay short', () => {
    expect(filtersToParams(DEFAULT_FILTERS).toString()).toBe('')
  })
  it('round-trips through the URL', () => {
    const filters = { ...DEFAULT_FILTERS, q: 'hero cycle', category: 'cycle', minPrice: '0', closingSoon: true, sort: 'price_low', page: 2 }
    expect(parse(filtersToParams(filters).toString())).toEqual(filters)
  })
  it('keeps a minimum price of 0', () => {
    expect(filtersToParams({ ...DEFAULT_FILTERS, minPrice: '0' }).get('min_price')).toBe('0')
  })
})

describe('apiQuery', () => {
  it('always sends sort and paging', () => {
    const q = new URLSearchParams(apiQuery(DEFAULT_FILTERS))
    expect(q.get('sort')).toBe('ending_soon')
    expect(q.get('limit')).toBe('12')
    expect(q.get('offset')).toBe('0')
  })
  it('turns the page number into an offset', () => {
    expect(new URLSearchParams(apiQuery({ ...DEFAULT_FILTERS, page: 3 })).get('offset')).toBe('24')
  })
  it('sends closing_soon as true and trims the search text', () => {
    const q = new URLSearchParams(apiQuery({ ...DEFAULT_FILTERS, closingSoon: true, q: '  cycle  ' }))
    expect(q.get('closing_soon')).toBe('true')
    expect(q.get('q')).toBe('cycle')
  })
  it('leaves out empty filters', () => {
    const q = new URLSearchParams(apiQuery(DEFAULT_FILTERS))
    for (const key of ['q', 'category', 'condition', 'min_price', 'max_price', 'closing_soon']) expect(q.has(key)).toBe(false)
  })
})

describe('helpers', () => {
  it('detects active filters but not sort or page', () => {
    expect(hasActiveFilters(DEFAULT_FILTERS)).toBe(false)
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, sort: 'newest', page: 4 })).toBe(false)
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, minPrice: '0' })).toBe(true)
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, q: '   ' })).toBe(false)
  })
  it('flags an impossible price range', () => {
    expect(isPriceRangeInvalid({ ...DEFAULT_FILTERS, minPrice: '500', maxPrice: '100' })).toBe(true)
    expect(isPriceRangeInvalid({ ...DEFAULT_FILTERS, minPrice: '100', maxPrice: '100' })).toBe(false)
    expect(isPriceRangeInvalid({ ...DEFAULT_FILTERS, minPrice: '100' })).toBe(false)
  })
})
