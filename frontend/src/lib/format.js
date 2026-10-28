// Display helpers: prices, countdown text, and the labels for backend enum values.

export const CATEGORIES = [
  { value: 'cycle', label: 'Cycles' },
  { value: 'calculator', label: 'Calculators' },
  { value: 'books', label: 'Books' },
  { value: 'electronics', label: 'Electronics' },
  { value: 'furniture', label: 'Furniture' },
  { value: 'other', label: 'Other' },
]

export const CONDITIONS = [
  { value: 'new', label: 'New' },
  { value: 'like_new', label: 'Like new' },
  { value: 'good', label: 'Good' },
  { value: 'fair', label: 'Fair' },
  { value: 'poor', label: 'Poor' },
]

export const SORTS = [
  { value: 'ending_soon', label: 'Ending soonest' },
  { value: 'newest', label: 'Newest' },
  { value: 'price_low', label: 'Price: low to high' },
  { value: 'price_high', label: 'Price: high to low' },
]

const labelOf = (list, value) => list.find((item) => item.value === value)?.label ?? value
export const categoryLabel = (value) => labelOf(CATEGORIES, value)
export const conditionLabel = (value) => labelOf(CONDITIONS, value)

/** Money is whole rupees: 12500 -> "₹12,500". */
export function formatRupees(amount) {
  return `₹${Number(amount).toLocaleString('en-IN')}`
}

const pad = (n) => String(n).padStart(2, '0')

/** Milliseconds left -> "2d 3h", "3h 12m", "12m 05s", "45s", or "Ended". */
export function formatRemaining(ms) {
  if (ms <= 0) return 'Ended'
  const total = Math.floor(ms / 1000)
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${pad(seconds)}s`
  return `${seconds}s`
}

/** How urgent a remaining time feels, used to colour the countdown. */
export function urgencyOf(ms) {
  if (ms <= 0) return 'ended'
  if (ms < 5 * 60 * 1000) return 'critical'
  if (ms < 60 * 60 * 1000) return 'soon'
  return 'normal'
}

/** "just now", "5m ago", "3h ago", "2d ago" for a past ISO time, measured against `nowMs`. */
export function timeAgo(iso, nowMs) {
  const seconds = Math.floor((nowMs - Date.parse(iso)) / 1000)
  if (seconds < 45) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${Math.max(1, minutes)}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}
