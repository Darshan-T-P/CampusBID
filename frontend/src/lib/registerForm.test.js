import { describe, expect, it } from 'vitest'
import { isEduEmail, passwordStrength, validateRegistration } from './registerForm'

const good = {
  email: 'asha@kongu.edu',
  displayName: 'Asha',
  year: '3',
  department: 'Computer Science',
  phone: '98765 43210',
  password: 'correct-horse-9',
  confirm: 'correct-horse-9',
}

describe('isEduEmail', () => {
  it('accepts .edu addresses, subdomains and any capitalisation', () => {
    for (const ok of ['a@kongu.edu', 'A@Kongu.EDU', ' a@cs.kongu.edu ']) expect(isEduEmail(ok), ok).toBe(true)
  })
  it('rejects everything else, including look-alikes', () => {
    for (const bad of ['a@gmail.com', 'a@college.ac.in', 'a@edu.com', 'a@college.edu.com', 'a@college.education', 'a@.edu', 'a.edu', '', 'a b@college.edu'])
      expect(isEduEmail(bad), bad).toBe(false)
  })
})

describe('validateRegistration', () => {
  it('accepts a complete, valid form', () => {
    expect(validateRegistration(good)).toEqual({})
  })
  it('flags every empty field at once', () => {
    const empty = { email: '', displayName: '', year: '', department: '', phone: '', password: '', confirm: '' }
    expect(Object.keys(validateRegistration(empty)).sort()).toEqual(['confirm', 'department', 'displayName', 'email', 'password', 'phone', 'year'])
  })
  it('explains a non-.edu email clearly', () => {
    expect(validateRegistration({ ...good, email: 'asha@gmail.com' }).email).toMatch(/must end in \.edu/)
    expect(validateRegistration({ ...good, email: 'not-an-email' }).email).toMatch(/valid email/)
  })
  it('requires a valid mobile number', () => {
    expect(validateRegistration({ ...good, phone: '' }).phone).toMatch(/Enter your mobile/)
    expect(validateRegistration({ ...good, phone: '12345' }).phone).toMatch(/valid mobile number/)
  })
  it('requires a password of at least 8 characters', () => {
    expect(validateRegistration({ ...good, password: 'short', confirm: 'short' }).password).toMatch(/at least 8/)
  })
  it('requires the two passwords to match', () => {
    expect(validateRegistration({ ...good, confirm: 'different-password' }).confirm).toMatch(/do not match/)
  })
  it('treats whitespace-only name and department as empty', () => {
    const errors = validateRegistration({ ...good, displayName: '   ', department: '  ' })
    expect(errors.displayName).toBeTruthy()
    expect(errors.department).toBeTruthy()
  })
})

describe('passwordStrength', () => {
  it('scores weak to strong', () => {
    expect(passwordStrength('').label).toBe('')
    expect(passwordStrength('abc').label).toBe('Too short')
    expect(passwordStrength('abcdefgh').label).toBe('Weak')
    expect(passwordStrength('abcdefghijkl').label).toBe('Fair')
    expect(passwordStrength('Abcdefghijkl1!').label).toBe('Strong')
  })
})
