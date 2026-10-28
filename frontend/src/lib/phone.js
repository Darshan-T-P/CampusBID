// Mobile numbers, the same rules as the server (backend/app/core/phone.py). The server has the last word.

const HELP = 'Enter a valid mobile number, like 98765 43210 or +91 98765 43210'

/** '98765 43210', '098765-43210', '+91 98765 43210' -> '+919876543210'. Returns null if it isn't a number. */
export function normalizePhone(raw) {
  let text = String(raw ?? '').trim().replace(/[\s\-().]/g, '')
  if (text.startsWith('+')) {
    const digits = text.slice(1)
    return /^\d+$/.test(digits) && digits.length >= 8 && digits.length <= 15 && digits[0] !== '0' ? `+${digits}` : null
  }
  if (!/^\d+$/.test(text)) return null
  if (text.length === 11 && text.startsWith('0')) text = text.slice(1)
  else if (text.length === 12 && text.startsWith('91')) text = text.slice(2)
  return text.length === 10 && '6789'.includes(text[0]) ? `+91${text}` : null
}

/** A message for the form, or null when the number is fine. `required` = blank is an error. */
export function phoneError(raw, { required = false } = {}) {
  if (!String(raw ?? '').trim()) return required ? 'Enter your mobile number' : null
  return normalizePhone(raw) ? null : HELP
}

/** '+919876543210' -> '+91 98765 43210' for display; other countries just get the + and digits. */
export function formatPhone(stored) {
  if (!stored) return ''
  const m = /^\+91(\d{5})(\d{5})$/.exec(stored)
  return m ? `+91 ${m[1]} ${m[2]}` : stored
}

/** wa.me wants the number with no plus sign. */
export const whatsappLink = (stored) => `https://wa.me/${stored.replace(/^\+/, '')}`
