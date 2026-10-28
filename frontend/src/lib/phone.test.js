import { describe, expect, it } from 'vitest'
import { formatPhone, normalizePhone, phoneError, whatsappLink } from './phone'

describe('normalizePhone', () => {
  it('turns the usual ways of typing an Indian mobile into one form', () => {
    for (const typed of ['9876543210', '98765 43210', '98765-43210', '098765 43210', '919876543210', '+91 98765 43210', ' (+91) 98765.43210 '])
      expect(normalizePhone(typed), typed).toBe('+919876543210')
  })
  it('keeps international numbers that carry their country code', () => {
    expect(normalizePhone('+1 (415) 555-0123')).toBe('+14155550123')
  })
  it('rejects things that are not numbers', () => {
    for (const bad of ['', '12345', '5876543210', '98765432', '+0123456789', '+12', '98765 4321a', 'call me', '+91']) expect(normalizePhone(bad), bad).toBeNull()
  })
})

describe('phoneError', () => {
  it('only complains about blank when it is required', () => {
    expect(phoneError('')).toBeNull()
    expect(phoneError('   ', { required: true })).toMatch(/Enter your mobile/)
  })
  it('explains a bad number', () => {
    expect(phoneError('12345')).toMatch(/valid mobile number/)
    expect(phoneError('98765 43210', { required: true })).toBeNull()
  })
})

describe('display helpers', () => {
  it('formats an Indian number in two groups and leaves others alone', () => {
    expect(formatPhone('+919876543210')).toBe('+91 98765 43210')
    expect(formatPhone('+14155550123')).toBe('+14155550123')
    expect(formatPhone(null)).toBe('')
  })
  it('builds a WhatsApp link without the plus sign', () => {
    expect(whatsappLink('+919876543210')).toBe('https://wa.me/919876543210')
  })
})
