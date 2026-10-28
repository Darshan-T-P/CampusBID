import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { ListingCard } from '../components/ListingCard'
import { useDebouncedField } from '../hooks/useDebouncedField'
import { CONDITIONS, SORTS } from '../lib/format'
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
  const { user, isSignedIn } = useAuth()
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

  const [showFilters, setShowFilters] = useState(false)

  const CATEGORY_TABS = [
    { value: '', label: 'All items', icon: 'grid' },
    { value: 'cycle', label: 'Cycles', icon: 'bike' },
    { value: 'calculator', label: 'Calculators', icon: 'calculator' },
    { value: 'books', label: 'Books', icon: 'book' },
    { value: 'electronics', label: 'Electronics', icon: 'monitor' },
    { value: 'furniture', label: 'Furniture', icon: 'chair' },
    { value: 'other', label: 'Other', icon: 'package' },
  ]

  return (
    <div className="browse-app">
      {isSignedIn ? (
        /* Returning students want auctions, not a sales pitch: a slim welcome and the feed right below. */
        <section className="app-hero app-hero-compact">
          <div>
            <h1 className="app-hero-title">Welcome back{user ? `, ${user.display_name.split(' ')[0]}` : ''}</h1>
            <p className="app-hero-desc">
              {data ? `${data.total} ${data.total === 1 ? 'auction is' : 'auctions are'} open right now.` : 'Browse what is open right now.'}
            </p>
          </div>
          <div className="app-hero-actions">
            <a href="#auctions-feed" className="btn btn-primary">Browse auctions</a>
            <Link to="/sell" className="btn btn-ghost">List an item</Link>
          </div>
        </section>
      ) : (
        <>
      {/* --- Landing Hero Section --- */}
      <section className="app-hero">
        <h1 className="app-hero-title">Buy and sell on campus through fair, timed auctions</h1>
        <p className="app-hero-desc">
          Graduating seniors list calculators, cycles, textbooks and dorm furniture. Verified students bid openly, and the highest bid when the timer ends wins.
        </p>
        <div className="app-hero-actions">
          <a href="#auctions-feed" className="btn btn-primary btn-lg">Browse auctions</a>
          <Link to="/sell" className="btn btn-ghost btn-lg">List an item</Link>
        </div>
        <div className="app-hero-perks">
          <span className="perk-item"><Icon name="shield" size={16} /> Verified campus students only</span>
          <span className="perk-item"><Icon name="list" size={16} /> Public bid history</span>
          <span className="perk-item"><Icon name="users" size={16} /> Handover on campus</span>
        </div>
      </section>

      {/* --- How Relay Works Feature Strip --- */}
      <section className="how-section">
        <div className="how-card">
          <span className="how-step">01</span>
          <h3 className="how-title">List an item</h3>
          <p className="how-desc">Add photos, set a starting price and a closing time between 10 minutes and 30 days.</p>
        </div>
        <div className="how-card">
          <span className="how-step">02</span>
          <h3 className="how-title">Bid openly</h3>
          <p className="how-desc">Every bid is public. A bid in the last 30 seconds extends the timer, so no one wins by sniping.</p>
        </div>
        <div className="how-card">
          <span className="how-step">03</span>
          <h3 className="how-title">Hand over on campus</h3>
          <p className="how-desc">The seller approves the winning bid, then you meet on campus to inspect the item and hand it over.</p>
        </div>
      </section>
        </>
      )}

      {/* --- Main Application Auction Feed --- */}
      <section id="auctions-feed" className="feed-section">
        {/* Category Tabs Bar */}
        <div className="category-tabs-bar" role="tablist" aria-label="Browse categories">
          {CATEGORY_TABS.map((tab) => {
            const isActive = filters.category === tab.value
            return (
              <button
                key={tab.value}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`category-pill ${isActive ? 'category-pill-active' : ''}`}
                onClick={() => update({ category: tab.value })}
              >
                <Icon name={tab.icon} size={17} className="category-pill-icon" />
                <span>{tab.label}</span>
              </button>
            )
          })}
        </div>

        {/* Search & Discovery Toolbar */}
        <div className="toolbar-card">
          <div className="search-bar-wrap">
            <svg className="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/>
              <path d="m21 21-4.3-4.3"/>
            </svg>
            <input
              type="search"
              className="search-input"
              placeholder="Search cycles, calculators, books, gear…"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
            {searchText && (
              <button type="button" className="search-clear-btn" onClick={() => setSearchText('')} aria-label="Clear search"><Icon name="x" size={14} /></button>
            )}
          </div>

          {/* Quick Sort Tabs */}
          <div className="sort-tabs-wrap">
            {SORTS.map((s) => (
              <button
                key={s.value}
                type="button"
                className={`sort-pill ${filters.sort === s.value ? 'sort-pill-active' : ''}`}
                onClick={() => update({ sort: s.value })}
              >
                                                                                {s.label}
              </button>
            ))}
            <button
              type="button"
              className={`filter-toggle-btn ${showFilters || hasActiveFilters(filters) ? 'filter-toggle-active' : ''}`}
              onClick={() => setShowFilters((v) => !v)}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
              </svg>
              <span>Filters</span>
              {filtered && <span className="filter-active-dot" />}
            </button>
          </div>
        </div>

        {/* Expandable Advanced Filters Drawer */}
        {showFilters && (
          <div className="advanced-filters-drawer">
            <div className="drawer-grid">
              <label className="drawer-field">
                <span className="drawer-label">Condition</span>
                <select value={filters.condition} onChange={(e) => update({ condition: e.target.value })}>
                  <option value="">Any condition</option>
                  {CONDITIONS.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              </label>

              <div className="drawer-field">
                <span className="drawer-label">Price Range (₹)</span>
                <div className="price-inputs-row">
                  <input
                    type="number"
                    min="0"
                    placeholder="Min ₹"
                    value={minText}
                    onChange={(e) => setMinText(e.target.value)}
                  />
                  <span className="price-dash">–</span>
                  <input
                    type="number"
                    min="0"
                    placeholder="Max ₹"
                    value={maxText}
                    onChange={(e) => setMaxText(e.target.value)}
                  />
                </div>
              </div>

              <div className="drawer-field drawer-field-checkbox">
                <label className="filter-check">
                  <input
                    type="checkbox"
                    checked={filters.closingSoon}
                    onChange={(e) => update({ closingSoon: e.target.checked })}
                  />
                  <span>Closing within 24h only</span>
                </label>
              </div>
            </div>

            {filtered && (
              <div className="drawer-actions">
                <button
                  type="button"
                  className="link-button"
                  onClick={() => setSearchParams(filtersToParams({ ...DEFAULT_FILTERS, sort: filters.sort }))}
                >
                  Reset all filters
                </button>
              </div>
            )}
          </div>
        )}

        {/* Feed Header with Live Stats & Active Pills */}
        <div className="feed-header">
          <div className="feed-header-left">
            <h2 className="feed-heading">
              {filters.category ? `${CATEGORY_TABS.find(t => t.value === filters.category)?.label || 'Items'}` : 'Open auctions'}
            </h2>
            {data && !priceRangeInvalid && (
              <span className="live-count-badge">
                {data.total} {data.total === 1 ? 'auction open' : 'auctions open'}
              </span>
            )}
          </div>
          {filtered && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setSearchParams(filtersToParams({ ...DEFAULT_FILTERS, sort: filters.sort }))}
            >
              Clear filters
            </button>
          )}
        </div>

        {priceRangeInvalid && (
          <p className="error" role="alert">
            The minimum price is higher than the maximum price.
          </p>
        )}

        {query.isPending && !priceRangeInvalid && (
          <div className="grid" aria-busy="true" aria-label="Loading auctions">
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="listing-card skeleton-card" aria-hidden="true">
                <div className="thumb skeleton" />
                <div className="listing-body">
                  <div className="skeleton skeleton-line" style={{ width: '78%' }} />
                  <div className="skeleton skeleton-line" style={{ width: '40%' }} />
                  <div className="skeleton skeleton-line skeleton-price" />
                  <div className="skeleton skeleton-line" style={{ width: '55%' }} />
                </div>
              </div>
            ))}
          </div>
        )}

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
    </div>
  )
}
