import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTERS } from './query'
import { describeWant, validateWant, wantFromFilters } from './wants'

describe('wantFromFilters', () => {
  it('uses the search words, category and price limit', () => {
    expect(wantFromFilters({ ...DEFAULT_FILTERS, q: ' cycle ', category: 'cycle', maxPrice: '2000' })).toEqual({ keywords: 'cycle', category: 'cycle', max_price: 2000 })
  })
  it('works with only one part', () => {
    expect(wantFromFilters({ ...DEFAULT_FILTERS, q: 'lamp' })).toEqual({ keywords: 'lamp', category: null, max_price: null })
    expect(wantFromFilters({ ...DEFAULT_FILTERS, category: 'books' })).toEqual({ keywords: '', category: 'books', max_price: null })
  })
  it('returns null when nothing narrows the search, and ignores a bad price', () => {
    expect(wantFromFilters(DEFAULT_FILTERS)).toBeNull()
    expect(wantFromFilters({ ...DEFAULT_FILTERS, maxPrice: 'abc' })).toBeNull()
    expect(wantFromFilters({ ...DEFAULT_FILTERS, minPrice: '100', condition: 'good' })).toBeNull() // only words, category and max price are alerts
  })
})

describe('describeWant', () => {
  it('reads like a sentence fragment', () => {
    expect(describeWant({ keywords: 'cycle', category: 'cycle', max_price: 2000 })).toBe('"cycle" · Cycles · under ₹2,000')
    expect(describeWant({ keywords: '', category: null, max_price: 500 })).toBe('under ₹500')
  })
})

describe('validateWant', () => {
  it('needs something to look for', () => {
    expect(validateWant({ keywords: '  ', category: '', maxPrice: '' })).toHaveProperty('form')
    expect(validateWant({ keywords: 'lamp', category: '', maxPrice: '' })).toEqual({})
    expect(validateWant({ keywords: '', category: 'books', maxPrice: '' })).toEqual({})
  })
  it('checks the price and length', () => {
    expect(validateWant({ keywords: 'x', category: '', maxPrice: '12.5' })).toHaveProperty('maxPrice')
    expect(validateWant({ keywords: 'x', category: '', maxPrice: '0' })).toHaveProperty('maxPrice')
    expect(validateWant({ keywords: 'x'.repeat(81), category: '', maxPrice: '' })).toHaveProperty('keywords')
  })
})
