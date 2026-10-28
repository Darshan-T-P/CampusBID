// Saved alerts ("wants"): turn a search into an alert, and describe one in words.

import { categoryLabel, formatRupees } from './format'

/** The alert body for the current Browse filters, or null if there is nothing worth alerting on. */
export function wantFromFilters(filters) {
  const keywords = filters.q.trim()
  const category = filters.category || null
  const maxPrice = filters.maxPrice !== '' && Number.isFinite(Number(filters.maxPrice)) && Number(filters.maxPrice) > 0 ? Number(filters.maxPrice) : null
  if (!keywords && !category && maxPrice === null) return null
  return { keywords, category, max_price: maxPrice }
}

/** '"cycle" · Cycles · under ₹2,000' */
export function describeWant(want) {
  const parts = []
  if (want.keywords) parts.push(`"${want.keywords}"`)
  if (want.category) parts.push(categoryLabel(want.category))
  if (want.max_price != null) parts.push(`under ${formatRupees(want.max_price)}`)
  return parts.join(' · ') || 'Any new listing'
}

/** Errors for the "new alert" form; the server re-checks everything. */
export function validateWant({ keywords, category, maxPrice }) {
  const errors = {}
  if (!keywords.trim() && !category && String(maxPrice).trim() === '') errors.form = 'Add a word, a category or a price limit'
  if (keywords.trim().length > 80) errors.keywords = 'Keep it under 80 characters'
  if (String(maxPrice).trim() !== '') {
    const n = Number(maxPrice)
    if (!Number.isInteger(n) || n < 1) errors.maxPrice = 'Enter a whole number of rupees'
  }
  return errors
}
