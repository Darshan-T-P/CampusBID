import { describe, expect, it } from 'vitest'
import { closedMessage, parseAmount, statusInfo, validateBid } from './bidding'

describe('parseAmount', () => {
  it('accepts whole positive numbers, with stray spaces or commas', () => {
    expect(parseAmount('500')).toBe(500)
    expect(parseAmount(' 1,250 ')).toBe(1250)
  })
  it('rejects everything else', () => {
    for (const bad of ['', '  ', '0', '-5', '12.5', '1e3', 'abc', '5 0', '₹500']) expect(parseAmount(bad)).toBeNull()
  })
  it('rejects numbers too big to be exact', () => {
    expect(parseAmount('99999999999999999999')).toBeNull()
  })
})

describe('validateBid', () => {
  it('asks for an amount', () => {
    expect(validateBid('', 500)).toBe('Enter an amount')
  })
  it('explains non-numbers', () => {
    expect(validateBid('12.5', 500)).toMatch(/whole number/)
  })
  it('states the minimum when the bid is too low, and accepts exactly the minimum', () => {
    expect(validateBid('499', 500)).toBe('The minimum bid is ₹500')
    expect(validateBid('500', 500)).toBeNull()
    expect(validateBid('900', 500)).toBeNull()
  })
  it('does not enforce a minimum when none is known', () => {
    expect(validateBid('1', null)).toBeNull()
  })
})

describe('statusInfo / closedMessage', () => {
  it('has a label for every status and falls back for unknown ones', () => {
    for (const s of ['active', 'pending_approval', 'reserved', 'completed', 'failed_pickup', 'rejected', 'unsold', 'cancelled']) {
      expect(statusInfo(s).label).toBeTruthy()
    }
    expect(statusInfo('mystery').label).toBe('mystery')
  })
  it('names the winner and price', () => {
    const msg = closedMessage({ status: 'completed', leading_bidder: 'Bea', current_price: 2600 })
    expect(msg).toBe('Sold to Bea for ₹2,600.')
  })
  it('has no message for an open listing', () => {
    expect(closedMessage({ status: 'active' })).toBeNull()
  })
})
