import { describe, expect, it } from 'vitest'
import { defaultMinRaise } from './raise'

describe('defaultMinRaise', () => {
  it('is about 5% of the starting price, rounded to a tidy number', () => {
    const expected = { 1: 1, 10: 1, 50: 2, 100: 5, 150: 5, 200: 10, 300: 10, 500: 25, 800: 50, 1800: 100, 4002: 200, 25000: 1000 }
    for (const [price, step] of Object.entries(expected)) expect(defaultMinRaise(Number(price)), price).toBe(step)
  })
  it('grows with the price and is never below one rupee', () => {
    const steps = [100, 500, 2000, 10000, 100000].map(defaultMinRaise)
    expect(steps).toEqual([...steps].sort((a, b) => a - b))
    expect(new Set(steps).size).toBe(steps.length)
    expect(defaultMinRaise(1)).toBeGreaterThanOrEqual(1)
  })
})
