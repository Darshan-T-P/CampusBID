// Rules for the sign-up form. They give instant, specific feedback; the server re-checks everything
// (including that the address really ends in .edu).

export const REQUIRED_EMAIL_SUFFIX = '.edu'

export const DEPARTMENTS = [
  'Computer Science',
  'Information Technology',
  'Artificial Intelligence and Data Science',
  'Electronics and Communication',
  'Electrical and Electronics',
  'Mechanical Engineering',
  'Civil Engineering',
  'Business Administration',
  'Other',
]

const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** True for an address whose domain ends in .edu (subdomains such as cs.college.edu count). */
export function isEduEmail(email) {
  const clean = email.trim().toLowerCase()
  return EMAIL_SHAPE.test(clean) && clean.endsWith(REQUIRED_EMAIL_SUFFIX)
}

/** A rough 0-4 score and label, only to nudge people toward a better password. */
export function passwordStrength(password) {
  if (!password) return { score: 0, label: '' }
  let score = 0
  if (password.length >= 8) score += 1
  if (password.length >= 12) score += 1
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1
  if (password.length < 8) score = Math.min(score, 1)
  return { score, label: ['Too short', 'Weak', 'Fair', 'Good', 'Strong'][score] }
}

/** One message per bad field; an empty object means the form is valid. */
export function validateRegistration(v) {
  const errors = {}
  const email = v.email.trim()
  if (!email) errors.email = 'Enter your campus email'
  else if (!EMAIL_SHAPE.test(email)) errors.email = 'Enter a valid email address'
  else if (!isEduEmail(email)) errors.email = `Use your campus email address: it must end in ${REQUIRED_EMAIL_SUFFIX}`

  const name = v.displayName.trim()
  if (!name) errors.displayName = 'Enter the name other students will see'
  else if (name.length > 80) errors.displayName = 'Keep your name under 80 characters'

  if (!v.year) errors.year = 'Choose your year of study'

  const department = v.department.trim()
  if (!department) errors.department = 'Enter your department'
  else if (department.length > 80) errors.department = 'Keep the department under 80 characters'

  if (!v.password) errors.password = 'Choose a password'
  else if (v.password.length < 8) errors.password = 'Use at least 8 characters'
  else if (v.password.length > 128) errors.password = 'Use at most 128 characters'

  if (!v.confirm) errors.confirm = 'Re-enter your password'
  else if (v.confirm !== v.password) errors.confirm = 'Passwords do not match'
  return errors
}
