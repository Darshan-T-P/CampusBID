import { describe, expect, it } from 'vitest'
import { validateForgot, validateReset } from './resetForm'

describe('validateForgot', () => {
  it('needs a well-formed email', () => {
    expect(validateForgot('')).toHaveProperty('email')
    expect(validateForgot('   ')).toHaveProperty('email')
    expect(validateForgot('nope')).toHaveProperty('email')
    expect(validateForgot(' asha@campus.edu ')).toEqual({})
  })
})

describe('validateReset', () => {
  const ok = { code: '123456', password: 'new-password-2', confirm: 'new-password-2' }
  it('accepts a good form', () => expect(validateReset(ok)).toEqual({}))
  it('wants exactly six digits', () => {
    for (const code of ['', '12345', '1234567', 'abcdef', '12 456']) expect(validateReset({ ...ok, code })).toHaveProperty('code')
  })
  it('checks the password length', () => {
    expect(validateReset({ ...ok, password: 'short', confirm: 'short' })).toHaveProperty('password')
    expect(validateReset({ ...ok, password: 'x'.repeat(129), confirm: 'x'.repeat(129) })).toHaveProperty('password')
    expect(validateReset({ ...ok, password: '', confirm: '' })).toHaveProperty('password')
  })
  it('requires the confirmation to match', () => {
    expect(validateReset({ ...ok, confirm: '' })).toHaveProperty('confirm')
    expect(validateReset({ ...ok, confirm: 'different-one' })).toHaveProperty('confirm')
  })
})
