// Rules for the "sell an item" form. These give instant feedback; the backend re-checks everything
// (and is the only one that can look inside a photo to confirm it really is an image).
import { parseAmount } from './bidding'

export const MAX_PHOTOS = 5
export const MAX_PHOTO_BYTES = 5 * 1024 * 1024
export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const MIN_DURATION_MS = 10 * 60 * 1000 // an auction needs a fair chance to be seen
export const MAX_DURATION_MS = 30 * 24 * 60 * 60 * 1000
export const MAX_PRICE = 10_000_000
export const MAX_TITLE = 120
export const MAX_DESCRIPTION = 5000

const HOUR = 60 * 60 * 1000
export const DURATION_PRESETS = [
  { label: '1 hour', ms: HOUR },
  { label: '6 hours', ms: 6 * HOUR },
  { label: '1 day', ms: 24 * HOUR },
  { label: '3 days', ms: 72 * HOUR },
  { label: '7 days', ms: 168 * HOUR },
]

const pad = (n) => String(n).padStart(2, '0')

/** A Date -> the "YYYY-MM-DDTHH:mm" text an <input type="datetime-local"> uses (in local time). */
export function toLocalInputValue(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** The text from a datetime-local input -> a Date (read as local time), or null if it isn't a real date. */
export function parseLocalInput(value) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** Check the chosen photo files. Returns a message or null. */
export function validatePhotos(files) {
  if (files.length === 0) return 'Add at least one photo'
  if (files.length > MAX_PHOTOS) return `You can add at most ${MAX_PHOTOS} photos`
  for (const file of files) {
    if (!PHOTO_TYPES.includes(file.type)) return `"${file.name}" isn't a JPEG, PNG or WebP image`
    if (file.size > MAX_PHOTO_BYTES) return `"${file.name}" is over ${MAX_PHOTO_BYTES / (1024 * 1024)} MB`
  }
  return null
}

function validatePrice(text, label) {
  if (String(text).trim() === '') return `Enter ${label}`
  const n = parseAmount(text)
  if (n === null) return `${label[0].toUpperCase()}${label.slice(1)} must be a whole number of rupees`
  if (n > MAX_PRICE) return `${label[0].toUpperCase()}${label.slice(1)} can be at most ₹${MAX_PRICE.toLocaleString('en-IN')}`
  return null
}

/**
 * Validate the whole form. `values` holds the text fields as typed, `files` the chosen photos and
 * `nowMs` the current SERVER time. Returns an object with one message per bad field (empty = all good).
 */
export function validateListing(values, files, nowMs) {
  const errors = {}
  if (!values.title.trim()) errors.title = 'Give your item a title'
  else if (values.title.trim().length > MAX_TITLE) errors.title = `Keep the title under ${MAX_TITLE} characters`
  if (!values.category) errors.category = 'Choose a category'
  if (!values.condition) errors.condition = 'Choose a condition'
  if (values.description.length > MAX_DESCRIPTION) errors.description = `Keep the description under ${MAX_DESCRIPTION} characters`

  const price = validatePrice(values.startingPrice, 'a starting price')
  if (price) errors.startingPrice = price
  const increment = validatePrice(values.minIncrement, 'a minimum bid increase')
  if (increment) errors.minIncrement = increment

  const closes = parseLocalInput(values.closesAt)
  if (!values.closesAt) errors.closesAt = 'Choose when the auction should end'
  else if (!closes) errors.closesAt = 'Choose a valid closing date and time'
  else if (closes.getTime() - nowMs < MIN_DURATION_MS) errors.closesAt = 'The auction must run for at least 10 minutes'
  else if (closes.getTime() - nowMs > MAX_DURATION_MS) errors.closesAt = 'The auction can run for at most 30 days'

  const photos = validatePhotos(files)
  if (photos) errors.photos = photos
  return errors
}
