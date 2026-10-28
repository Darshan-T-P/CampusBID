// Rules for the Profile page forms. The server re-checks everything; these give instant feedback.

/** Errors for the "edit my details" form. Department and year are optional here (older accounts may lack them). */
export function validateProfile(v) {
  const errors = {}
  const name = v.displayName.trim()
  if (!name) errors.displayName = 'Enter the name other students will see'
  else if (name.length > 80) errors.displayName = 'Keep your name under 80 characters'
  if (v.department.trim().length > 80) errors.department = 'Keep the department under 80 characters'
  return errors
}

/** Only the fields that differ from the saved profile, in the shape PATCH /me expects. Blank department/year -> null. */
export function profileChanges(user, v) {
  const changes = {}
  if (v.displayName.trim() !== user.display_name) changes.display_name = v.displayName.trim()
  const department = v.department.trim() || null
  if (department !== (user.department ?? null)) changes.department = department
  const year = v.year === '' ? null : Number(v.year)
  if (year !== (user.year_of_study ?? null)) changes.year_of_study = year
  return changes
}

/** Errors for the "change my password" form. */
export function validatePasswordChange({ current, next, confirm }) {
  const errors = {}
  if (!current) errors.current = 'Enter your current password'
  if (!next) errors.next = 'Choose a new password'
  else if (next.length < 8) errors.next = 'Use at least 8 characters'
  else if (next.length > 128) errors.next = 'Use at most 128 characters'
  else if (next === current) errors.next = 'Choose a password different from your current one'
  if (!confirm) errors.confirm = 'Re-enter the new password'
  else if (confirm !== next) errors.confirm = 'Passwords do not match'
  return errors
}

/** "Member since Oct 2026". */
export function memberSince(iso) {
  return new Date(iso).toLocaleDateString([], { month: 'short', year: 'numeric' })
}
