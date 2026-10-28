// Rules for the "forgot password" form. The server re-checks all of it.

const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Step 1: only an email is needed. */
export function validateForgot(email) {
  const clean = email.trim()
  if (!clean) return { email: 'Enter your campus email' }
  if (!EMAIL_SHAPE.test(clean)) return { email: 'Enter a valid email address' }
  return {}
}

/** Step 2: the emailed code plus a new password typed twice. One message per bad field. */
export function validateReset(v) {
  const errors = {}
  if (!/^\d{6}$/.test(v.code)) errors.code = 'Enter the 6-digit code from the email'
  if (!v.password) errors.password = 'Choose a new password'
  else if (v.password.length < 8) errors.password = 'Use at least 8 characters'
  else if (v.password.length > 128) errors.password = 'Use at most 128 characters'
  if (!v.confirm) errors.confirm = 'Re-enter your new password'
  else if (v.confirm !== v.password) errors.confirm = 'Passwords do not match'
  return errors
}
