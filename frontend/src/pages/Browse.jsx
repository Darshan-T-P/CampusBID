import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { ListingCard } from '../components/ListingCard'
import { useDebouncedField } from '../hooks/useDebouncedField'
import { CATEGORIES, CONDITIONS, SORTS } from '../lib/format'
import {
  DEFAULT_FILTERS,
  PAGE_SIZE,
  apiQuery,
  filtersFromParams,
  filtersToParams,
  hasActiveFilters,
  isPriceRangeInvalid,
} from '../lib/query'

export function Browse() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = filtersFromParams(searchParams)
  const priceRangeInvalid = isPriceRangeInvalid(filters)

  // Any change to a filter goes through here: update the URL, and go back to page 1
  // (unless the change IS the page).
  // It starts from the URL as it is RIGHT NOW, not from this render's `filters`: two debounced
  // fields (min and max price) can commit in the same moment, and each must see the other's change.
  function update(changes) {
    const current = filtersFromParams(new URLSearchParams(window.location.search))
    const next = { ...current, ...(changes.page === undefined ? { page: 1 } : {}), ...changes }
    setSearchParams(filtersToParams(next))
  }

  const [searchText, setSearchText] = useDebouncedField(filters.q, (q) => update({ q }))
  const [minText, setMinText] = useDebouncedField(filters.minPrice, (minPrice) => update({ minPrice }), 600)
  const [maxText, setMaxText] = useDebouncedField(filters.maxPrice, (maxPrice) => update({ maxPrice }), 600)

  const query = useQuery({
    queryKey: ['listings', apiQuery(filters)],
    queryFn: () => api(`/listings?${apiQuery(filters)}`),
    enabled: !priceRangeInvalid, // an impossible range can't match anything: don't bother the server
    placeholderData: keepPreviousData, // keep showing the old page while the next one loads
    refetchInterval: 15_000, // other people's bids and new listings show up without a reload
  })

  const data = query.data
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  const filtered = hasActiveFilters(filters)

  return (
    <section>
      <div className="browse-hero">
        <div className="browse-hero-main">
          <span className="badge badge-info hero-tag">🎓 Campus Marketplace</span>
          <h1 className="browse-hero-title">Live Campus Auctions</h1>
          <p className="browse-hero-subtitle">
            Bid on cycles, calculators, books & dorm essentials from graduating seniors. Transparent timers, verified students only.
          </p>
        </div>
        {data && !priceRangeInvalid && (
          <div className="browse-stat-card">
            <span className="browse-stat-num">{data.total}</span>
            <span className="browse-stat-label">{data.total === 1 ? 'auction live' : 'auctions live'}</span>
            {filtered && <span className="browse-stat-sub">(filtered)</span>}
          </div>
        )}
      </div>

      <div className="filters card">
        <label className="filter filter-search">
          <span>Search</span>
          <input
            type="search"
            placeholder="Cycle, calculator, textbook…"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
        </label>
        <label className="filter">
          <span>Category</span>
          <select value={filters.category} onChange={(e) => update({ category: e.target.value })}>
            <option value="">All</option>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label className="filter">
          <span>Condition</span>
          <select value={filters.condition} onChange={(e) => update({ condition: e.target.value })}>
            <option value="">Any</option>
            {CONDITIONS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label className="filter filter-price">
          <span>Min ₹</span>
          <input type="number" min="0" inputMode="numeric" value={minText} onChange={(e) => setMinText(e.target.value)} />
        </label>
        <label className="filter filter-price">
          <span>Max ₹</span>
          <input type="number" min="0" inputMode="numeric" value={maxText} onChange={(e) => setMaxText(e.target.value)} />
        </label>
        <label className="filter">
          <span>Sort by</span>
          <select value={filters.sort} onChange={(e) => update({ sort: e.target.value })}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-check" title="Auctions ending within the next 24 hours">
          <input
            type="checkbox"
            checked={filters.closingSoon}
            onChange={(e) => update({ closingSoon: e.target.checked })}
          />
          Closing soon
        </label>
        {filtered && (
          <button type="button" className="btn btn-ghost" onClick={() => setSearchParams(filtersToParams({ ...DEFAULT_FILTERS, sort: filters.sort }))}>
            Clear filters
          </button>
        )}
      </div>

      {priceRangeInvalid && (
        <p className="error" role="alert">
          The minimum price is higher than the maximum, so nothing can match.
        </p>
      )}

      {query.isPending && !priceRangeInvalid && <p className="muted center">Loading auctions…</p>}

      {query.isError && (
        <div className="error" role="alert">
          {errorMessage(query.error)}{' '}
          <button type="button" className="link-button" onClick={() => query.refetch()}>
            Try again
          </button>
        </div>
      )}

      {data && !priceRangeInvalid && (
        <>
          {data.items.length === 0 ? (
            <div className="empty card">
              {data.total > 0 ? (
                <>
                  <p>There's nothing on this page.</p>
                  <button type="button" className="btn btn-primary" onClick={() => update({ page: 1 })}>
                    Back to the first page
                  </button>
                </>
              ) : filtered ? (
                <>
                  <p>No open auctions match your filters.</p>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => setSearchParams(filtersToParams({ ...DEFAULT_FILTERS, sort: filters.sort }))}
                  >
                    Clear filters
                  </button>
                </>
              ) : (
                <p>No auctions are open right now. Check back soon!</p>
              )}
            </div>
          ) : (
            <div className={`grid ${query.isPlaceholderData ? 'grid-stale' : ''}`}>
              {data.items.map((listing) => (
                <ListingCard key={listing.id} listing={listing} />
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <nav className="pager" aria-label="Pages">
              <button className="btn btn-ghost" disabled={filters.page <= 1} onClick={() => update({ page: filters.page - 1 })}>
                ← Previous
              </button>
              <span className="muted">
                Page {filters.page} of {totalPages}
              </span>
              <button
                className="btn btn-ghost"
                disabled={filters.page >= totalPages}
                onClick={() => update({ page: filters.page + 1 })}
              >
                Next →
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  )
}
