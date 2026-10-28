import { describe, expect, it } from 'vitest'
import { memberSince, profileChanges, validatePasswordChange, validateProfile } from './profileForm'

const user = { display_name: 'Asha K', department: 'Civil', year_of_study: 3 }
const same = { displayName: 'Asha K', department: 'Civil', year: '3' }

describe('validateProfile', () => {
  it('accepts a normal profile', () => {
    expect(validateProfile(same)).toEqual({})
  })
  it('needs a name, and keeps lengths sane', () => {
    expect(validateProfile({ ...same, displayName: '   ' }).displayName).toBeTruthy()
    expect(validateProfile({ ...same, displayName: 'x'.repeat(81) }).displayName).toBeTruthy()
    expect(validateProfile({ ...same, department: 'x'.repeat(81) }).department).toBeTruthy()
  })
  it('lets department be empty', () => {
    expect(validateProfile({ ...same, department: '' })).toEqual({})
  })
})

describe('profileChanges', () => {
  it('reports nothing for an untouched form, even with stray spaces', () => {
    expect(profileChanges(user, same)).toEqual({})
    expect(profileChanges(user, { ...same, displayName: '  Asha K ' })).toEqual({})
  })
  it('reports exactly what changed', () => {
    expect(profileChanges(user, { ...same, displayName: 'Asha Kumar', year: '4' })).toEqual({ display_name: 'Asha Kumar', year_of_study: 4 })
  })
  it('turns a cleared department or year into null', () => {
    expect(profileChanges(user, { ...same, department: '  ', year: '' })).toEqual({ department: null, year_of_study: null })
  })
  it('treats missing values on an older account as null, not as a change', () => {
    expect(profileChanges({ display_name: 'A' }, { displayName: 'A', department: '', year: '' })).toEqual({})
  })
})

describe('validatePasswordChange', () => {
  const ok = { current: 'old-password', next: 'a-new-password', confirm: 'a-new-password' }
  it('accepts a valid change', () => {
    expect(validatePasswordChange(ok)).toEqual({})
  })
  it('requires every field', () => {
    expect(Object.keys(validatePasswordChange({ current: '', next: '', confirm: '' })).sort()).toEqual(['confirm', 'current', 'next'])
  })
  it('wants at least 8 characters and something new', () => {
    expect(validatePasswordChange({ ...ok, next: 'short', confirm: 'short' }).next).toMatch(/at least 8/)
    expect(validatePasswordChange({ current: 'same-password', next: 'same-password', confirm: 'same-password' }).next).toMatch(/different/)
  })
  it('wants the confirmation to match', () => {
    expect(validatePasswordChange({ ...ok, confirm: 'something-else' }).confirm).toMatch(/do not match/)
  })
})

describe('memberSince', () => {
  it('shows month and year', () => {
    expect(memberSince('2026-10-28T10:00:00Z')).toMatch(/2026/)
  })
})

describe('profileChanges and the results-email switch', () => {
  const user = { display_name: 'Asha', department: null, year_of_study: null, phone: null, notify_by_email: true }
  const same = { displayName: 'Asha', department: '', year: '', phone: '' }
  it('sends nothing when the switch is untouched or not part of the form', () => {
    expect(profileChanges(user, same)).toEqual({})
    expect(profileChanges(user, { ...same, notifyByEmail: true })).toEqual({})
  })
  it('sends the new value when it is flipped, in both directions', () => {
    expect(profileChanges(user, { ...same, notifyByEmail: false })).toEqual({ notify_by_email: false })
    expect(profileChanges({ ...user, notify_by_email: false }, { ...same, notifyByEmail: true })).toEqual({ notify_by_email: true })
  })
  it('treats an older profile without the field as "on"', () => {
    expect(profileChanges({ ...user, notify_by_email: undefined }, { ...same, notifyByEmail: true })).toEqual({})
  })
})
