import { describe, expect, it } from 'vitest'
import { basisLabel, describeSuggestion, hasSuggestion } from './pricing'

const full = { count: 4, basis: 'similar', low: 2000, median: 2100, high: 2200, suggested_start: 1450 }

describe('hasSuggestion', () => {
  it('needs at least three sales and a median', () => {
    expect(hasSuggestion(full)).toBe(true)
    expect(hasSuggestion({ count: 2, median: null })).toBe(false)
    expect(hasSuggestion({ count: 5, median: null })).toBe(false)
    expect(hasSuggestion(undefined)).toBe(false)
  })
})

describe('describeSuggestion', () => {
  it('states the range, the typical price, the number of sales and a starting price', () => {
    const d = describeSuggestion(full, 'good')
    expect(d.sold).toBe('Similar items sold for ₹2,000 to ₹2,200 (typically ₹2,100, from 4 sales).')
    expect(d.start).toBe('A starting price around ₹1,450 tends to invite early bids.')
  })
  it('does not show a "to" range when every sale was the same price', () => {
    expect(describeSuggestion({ ...full, low: 2100, high: 2100 }, 'good').sold).toContain('sold for ₹2,100 (typically')
  })
  it('says nothing when there is not enough to go on', () => {
    expect(describeSuggestion({ count: 1 }, 'good')).toBeNull()
  })
})

describe('basisLabel', () => {
  it('names the group of past sales', () => {
    expect(basisLabel({ basis: 'similar' }, 'good')).toBe('Similar items')
    expect(basisLabel({ basis: 'condition' }, 'like_new')).toBe('Like new items in this category')
    expect(basisLabel({ basis: 'category' }, 'good')).toBe('Items in this category')
  })
})
