// Browse filters <-> the page URL (?q=cycle&category=cycle&page=2) <-> the API query string.
// Keeping filters in the URL means a filtered view can be shared, and the back button works.

export const PAGE_SIZE = 12

export const DEFAULT_FILTERS = {
  q: '',
  category: '',
  condition: '',
  minPrice: '',
  maxPrice: '',
  closingSoon: false,
  sort: 'ending_soon',
  page: 1,
}

/** Read filters from URLSearchParams, falling back to defaults for anything missing or bad. */
export function filtersFromParams(params) {
  const page = Number.parseInt(params.get('page') ?? '', 10)
  return {
    q: params.get('q') ?? '',
    category: params.get('category') ?? '',
    condition: params.get('condition') ?? '',
    minPrice: params.get('min_price') ?? '',
    maxPrice: params.get('max_price') ?? '',
    closingSoon: params.get('closing_soon') === '1',
    sort: params.get('sort') || DEFAULT_FILTERS.sort,
    page: Number.isInteger(page) && page > 0 ? page : 1,
  }
}

/** The shorter, user-facing URL form: only non-default values appear. */
export function filtersToParams(filters) {
  const params = new URLSearchParams()
  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.category) params.set('category', filters.category)
  if (filters.condition) params.set('condition', filters.condition)
  if (filters.minPrice !== '') params.set('min_price', filters.minPrice)
  if (filters.maxPrice !== '') params.set('max_price', filters.maxPrice)
  if (filters.closingSoon) params.set('closing_soon', '1')
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set('sort', filters.sort)
  if (filters.page > 1) params.set('page', String(filters.page))
  return params
}

/** The query string the backend's GET /listings expects. */
export function apiQuery(filters, pageSize = PAGE_SIZE) {
  const params = new URLSearchParams()
  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.category) params.set('category', filters.category)
  if (filters.condition) params.set('condition', filters.condition)
  if (filters.minPrice !== '') params.set('min_price', filters.minPrice)
  if (filters.maxPrice !== '') params.set('max_price', filters.maxPrice)
  if (filters.closingSoon) params.set('closing_soon', 'true')
  params.set('sort', filters.sort)
  params.set('limit', String(pageSize))
  params.set('offset', String((filters.page - 1) * pageSize))
  return params.toString()
}

/** True when any filter (not sort or page) is narrowing the results. */
export function hasActiveFilters(filters) {
  return Boolean(
    filters.q.trim() ||
      filters.category ||
      filters.condition ||
      filters.minPrice !== '' ||
      filters.maxPrice !== '' ||
      filters.closingSoon,
  )
}

/** Both prices set and the minimum is above the maximum: nothing can match. */
export function isPriceRangeInvalid(filters) {
  if (filters.minPrice === '' || filters.maxPrice === '') return false
  return Number(filters.minPrice) > Number(filters.maxPrice)
}
