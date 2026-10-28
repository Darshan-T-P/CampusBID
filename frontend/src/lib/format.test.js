import { describe, expect, it } from 'vitest'
import { categoryLabel, conditionLabel, formatRemaining, formatRupees, timeAgo, urgencyOf } from './format'

const SEC = 1000
const MIN = 60 * SEC
const HOUR = 60 * MIN
const DAY = 24 * HOUR

describe('formatRemaining', () => {
  it('shows "Ended" at zero or below', () => {
    expect(formatRemaining(0)).toBe('Ended')
    expect(formatRemaining(-5000)).toBe('Ended')
  })
  it('counts seconds, minutes, hours and days', () => {
    expect(formatRemaining(45 * SEC)).toBe('45s')
    expect(formatRemaining(12 * MIN + 5 * SEC)).toBe('12m 05s')
    expect(formatRemaining(3 * HOUR + 12 * MIN + 59 * SEC)).toBe('3h 12m')
    expect(formatRemaining(2 * DAY + 3 * HOUR + 30 * MIN)).toBe('2d 3h')
  })
  it('rounds partial seconds down so it never shows time that is already gone', () => {
    expect(formatRemaining(1999)).toBe('1s')
    expect(formatRemaining(999)).toBe('0s')
  })
})

describe('urgencyOf', () => {
  it('escalates as the end approaches', () => {
    expect(urgencyOf(-1)).toBe('ended')
    expect(urgencyOf(4 * MIN)).toBe('critical')
    expect(urgencyOf(30 * MIN)).toBe('soon')
    expect(urgencyOf(3 * HOUR)).toBe('normal')
  })
})

describe('formatRupees', () => {
  it('uses the rupee sign and Indian digit grouping', () => {
    expect(formatRupees(500)).toBe('₹500')
    expect(formatRupees(125000)).toBe('₹1,25,000')
  })
})

describe('labels', () => {
  it('maps backend values to friendly names and falls back to the raw value', () => {
    expect(categoryLabel('cycle')).toBe('Cycles')
    expect(conditionLabel('like_new')).toBe('Like new')
    expect(categoryLabel('mystery')).toBe('mystery')
  })
})

describe('timeAgo', () => {
  const now = Date.parse('2026-05-01T12:00:00Z')
  const ago = (ms) => new Date(now - ms).toISOString()
  it('reads naturally at each scale', () => {
    expect(timeAgo(ago(10 * SEC), now)).toBe('just now')
    expect(timeAgo(ago(50 * SEC), now)).toBe('1m ago')
    expect(timeAgo(ago(5 * MIN), now)).toBe('5m ago')
    expect(timeAgo(ago(3 * HOUR), now)).toBe('3h ago')
    expect(timeAgo(ago(2 * DAY), now)).toBe('2d ago')
  })
  it('treats a time slightly in the future (clock skew) as just now', () => {
    expect(timeAgo(ago(-5000), now)).toBe('just now')
  })
})
