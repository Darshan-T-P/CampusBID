import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { AutoBidList } from '../components/AutoBidList'
import { BidHistory } from '../components/BidHistory'
import { BidPanel } from '../components/BidPanel'
import { Icon } from '../components/Icon'
import { ImageGallery } from '../components/ImageGallery'
import { categoryLabel, conditionLabel, formatRupees, yearLabel } from '../lib/format'

const LIVE_MS = 2500 // while the auction is open, so two browsers see each other's bids almost at once
const IDLE_MS = 20_000 // once it has ended, nothing changes quickly

export function ListingPage() {
  const { id } = useParams()
  const location = useLocation()
  const { isSignedIn, user } = useAuth()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('overview') // 'overview' | 'bids' | 'autobids' | 'safety'

  // The only thing we poll is the listing itself; everything else refreshes when it changes.
  const listingQuery = useQuery({
    queryKey: ['listing', id],
    queryFn: () => api(`/listings/${id}`),
    refetchInterval: (query) => (query.state.data?.status === 'active' ? LIVE_MS : IDLE_MS),
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
  })
  const listing = listingQuery.data

  const bidsQuery = useQuery({
    queryKey: ['bids', id],
    queryFn: () => api(`/listings/${id}/bids`),
    enabled: listing !== undefined,
  })

  const isOpen = listing?.status === 'active'
  const myBidsQuery = useQuery({
    queryKey: ['my-bids'],
    queryFn: () => api('/me/bids'),
    enabled: isSignedIn && listing !== undefined,
  })
  const myBid = myBidsQuery.data?.find((row) => row.listing.id === Number(id))

  // Automatic bidding: my own maximum, and everyone's (public).
  const myAutoQuery = useQuery({
    queryKey: ['my-auto-bids'],
    queryFn: () => api('/me/auto-bids'),
    enabled: isSignedIn && listing !== undefined,
  })
  const myMax = myAutoQuery.data?.find((row) => row.listing_id === Number(id))?.max_amount ?? null
  const autoBidsQuery = useQuery({
    queryKey: ['auto-bids', id],
    queryFn: () => api(`/listings/${id}/auto-bids`),
    enabled: listing !== undefined,
    refetchInterval: isOpen ? 5000 : false,
  })

  // Someone bid (or the auction changed state): refresh the history and my standing.
  const marker = listing ? `${listing.bid_count}:${listing.status}` : null
  const lastMarker = useRef(null)
  useEffect(() => {
    if (marker !== null && lastMarker.current !== null && lastMarker.current !== marker) {
      queryClient.invalidateQueries({ queryKey: ['bids', id] })
      queryClient.invalidateQueries({ queryKey: ['my-bids'] })
      queryClient.invalidateQueries({ queryKey: ['auto-bids', id] })
    }
    lastMarker.current = marker
  }, [marker, id, queryClient])

  useEffect(() => {
    if (listing) document.title = `${listing.title} · Relay`
    return () => {
      document.title = 'Relay'
    }
  }, [listing?.title]) // eslint-disable-line react-hooks/exhaustive-deps

  if (listingQuery.isPending) {
    return (
      <div className="listing-loading-container">
        <div className="loading-spinner" />
        <p className="muted">Loading auction details…</p>
      </div>
    )
  }

  if (listingQuery.isError) {
    const notFound = listingQuery.error instanceof ApiError && listingQuery.error.status === 404
    return (
      <section className="center error-page-card">
        <h1>{notFound ? "This auction doesn't exist" : "Couldn't load this auction"}</h1>
        {!notFound && <p className="error">{errorMessage(listingQuery.error)}</p>}
        <p>
          {!notFound && (
            <button type="button" className="btn btn-ghost" onClick={() => listingQuery.refetch()}>
              Try again
            </button>
          )}{' '}
          <Link to="/" className="btn btn-primary">← Back to browsing</Link>
        </p>
      </section>
    )
  }

  const sellerInitials = listing.seller.display_name
    ? listing.seller.display_name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U'

  return (
    <div className="listing-page-wrap">
      {location.state?.saved && (
        <div className="success-banner" role="status">
          <Icon name="check" size={16} /> Changes saved successfully.
        </div>
      )}
      {location.state?.published && (
        <div className="success-banner" role="status">
          <Icon name="check" size={16} /> Your listing is live! Verified students can start bidding.
        </div>
      )}

      {/* Top Navigation & Action Bar */}
      <div className="listing-top-nav">
        <Link to="/" className="back-nav-btn">
          <Icon name="arrowLeft" size={16} /> All auctions
        </Link>
        {isOpen && user?.id === listing.seller.id && (
          <Link to={`/listings/${listing.id}/edit`} className="btn btn-ghost btn-sm">
            Edit listing
          </Link>
        )}
      </div>

      {/* Title & Status Badges */}
      <div className="listing-header-hero">
        <h1 className="listing-h1">{listing.title}</h1>
        <div className="listing-badges-bar">
          <span className="listing-badge listing-badge-cat">
            <Icon name="grid" size={13} /> {categoryLabel(listing.category)}
          </span>
          <span className="listing-badge listing-badge-cond">
            {conditionLabel(listing.condition)}
          </span>
          {listing.handover_spot && (
            <span className="listing-badge listing-badge-spot" title="Designated Campus Meetup Spot">
              <Icon name="pin" size={13} /> {listing.handover_spot}
            </span>
          )}
          {isOpen ? (
            <span className="listing-badge listing-badge-live">
              <span className="pulse-dot" /> Live Auction
            </span>
          ) : (
            <span className="listing-badge listing-badge-closed">Bidding closed</span>
          )}
        </div>
      </div>

      {/* Main Two-Column Auction Layout */}
      <div className="detail-grid">
        {/* Left Column: Gallery + Interactive Tabbed Hub */}
        <div className="area-gallery-and-tabs">
          <div className="area-gallery">
            <ImageGallery images={listing.images} title={listing.title} />
          </div>

          {/* Interactive Activity & Details Tabs */}
          <div className="listing-tabs-container">
            <div className="listing-tabs-nav" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'overview'}
                className={`listing-tab-btn ${activeTab === 'overview' ? 'listing-tab-active' : ''}`}
                onClick={() => setActiveTab('overview')}
              >
                <Icon name="package" size={16} /> Overview & Specs
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'bids'}
                className={`listing-tab-btn ${activeTab === 'bids' ? 'listing-tab-active' : ''}`}
                onClick={() => setActiveTab('bids')}
              >
                <Icon name="trend" size={16} /> Live Bids ({listing.bid_count})
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'autobids'}
                className={`listing-tab-btn ${activeTab === 'autobids' ? 'listing-tab-active' : ''}`}
                onClick={() => setActiveTab('autobids')}
              >
                <Icon name="shield" size={16} /> Auto-Bids ({autoBidsQuery.data?.length ?? 0})
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'safety'}
                className={`listing-tab-btn ${activeTab === 'safety' ? 'listing-tab-active' : ''}`}
                onClick={() => setActiveTab('safety')}
              >
                <Icon name="pin" size={16} /> Handover & Safety
              </button>
            </div>

            <div className="listing-tab-content">
              {activeTab === 'overview' && (
                <div className="tab-pane-overview">
                  <div className="section-card">
                    <h3 className="section-subtitle">About this item</h3>
                    <p className="description">{listing.description || 'The seller has not provided additional description notes.'}</p>
                    {listing.edited_at && (
                      <p className="muted small edited-note">
                        Last edited {new Date(listing.edited_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                      </p>
                    )}
                  </div>

                  {/* Campus Handover Spot Card */}
                  {listing.handover_spot && (
                    <div className="handover-spot-card">
                      <div className="handover-spot-icon">
                        <Icon name="pin" size={20} />
                      </div>
                      <div className="handover-spot-body">
                        <strong className="handover-spot-title">Campus Handover Spot: {listing.handover_spot}</strong>
                        <p className="handover-spot-desc">
                          In-person campus handover. Meet during daylight in a public area. Inspect and test the item thoroughly before paying via direct UPI or cash.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Verified Student Seller Card */}
                  <div className="seller-profile-card">
                    <div className="seller-avatar">{sellerInitials}</div>
                    <div className="seller-details">
                      <div className="seller-name-row">
                        <strong className="seller-name">{listing.seller.display_name}</strong>
                        <span className="verified-badge-chip">
                          <Icon name="shield" size={13} /> Verified Student
                        </span>
                      </div>
                      <p className="seller-meta">
                        {[yearLabel(listing.seller.year_of_study), listing.seller.department].filter(Boolean).join(' · ') || 'Enrolled Student'}
                      </p>
                    </div>
                  </div>

                  {/* Item Specs Table */}
                  <div className="specs-table-card">
                    <h3 className="section-subtitle">Auction Specifications</h3>
                    <div className="specs-grid">
                      <div className="spec-item">
                        <span className="spec-label">Category</span>
                        <strong className="spec-val">{categoryLabel(listing.category)}</strong>
                      </div>
                      <div className="spec-item">
                        <span className="spec-label">Condition</span>
                        <strong className="spec-val">{conditionLabel(listing.condition)}</strong>
                      </div>
                      <div className="spec-item">
                        <span className="spec-label">Starting Price</span>
                        <strong className="spec-val">{formatRupees(listing.starting_price)}</strong>
                      </div>
                      <div className="spec-item">
                        <span className="spec-label">Min Increment</span>
                        <strong className="spec-val">{formatRupees(listing.min_increment)}</strong>
                      </div>
                      <div className="spec-item">
                        <span className="spec-label">Handover Spot</span>
                        <strong className="spec-val">{listing.handover_spot || 'Campus Public Area'}</strong>
                      </div>
                      <div className="spec-item">
                        <span className="spec-label">Auction ID</span>
                        <strong className="spec-val">#{listing.id}</strong>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'bids' && (
                <div className="tab-pane-bids">
                  <div className="tab-pane-header">
                    <h3 className="section-subtitle">
                      Live Bid History {listing.bid_count > 0 && <span className="muted">({listing.bid_count} placed)</span>}
                    </h3>
                    {isOpen && (
                      <span className="live-stream-indicator">
                        <span className="pulse-dot" /> Live sync
                      </span>
                    )}
                  </div>
                  {bidsQuery.isPending ? (
                    <p className="muted">Loading bids…</p>
                  ) : (
                    <BidHistory bids={bidsQuery.data ?? []} />
                  )}
                </div>
              )}

              {activeTab === 'autobids' && (
                <div className="tab-pane-autobids">
                  <div className="tab-pane-header">
                    <h3 className="section-subtitle">
                      Automatic Proxy Maximums {autoBidsQuery.data?.length > 0 && <span className="muted">({autoBidsQuery.data.length})</span>}
                    </h3>
                  </div>
                  <p className="muted small info-banner">
                    <Icon name="shield" size={14} /> Maximum ceilings are transparent and visible to all students. The system only bids on your behalf as much as necessary to maintain the lead.
                  </p>
                  <AutoBidList autoBids={autoBidsQuery.data ?? []} />
                </div>
              )}

              {activeTab === 'safety' && (
                <div className="tab-pane-safety">
                  <h3 className="section-subtitle">Campus Handover Protocol</h3>
                  <div className="safety-steps-grid">
                    <div className="safety-step-card">
                      <div className="safety-step-num">01</div>
                      <h4>Verified Student Meeting</h4>
                      <p>Both buyers and sellers are registered students with verified institutional emails.</p>
                    </div>
                    <div className="safety-step-card">
                      <div className="safety-step-num">02</div>
                      <h4>Public Campus Spot</h4>
                      <p>Meet in daylight at {listing.handover_spot || 'a prominent campus spot like the Library Gate or Canteen'}.</p>
                    </div>
                    <div className="safety-step-card">
                      <div className="safety-step-num">03</div>
                      <h4>Inspect Before Settling</h4>
                      <p>Check the physical condition, functionality, and serial numbers before making payment.</p>
                    </div>
                    <div className="safety-step-card">
                      <div className="safety-step-num">04</div>
                      <h4>Direct Peer-to-Peer</h4>
                      <p>Zero platform commission. Settle directly with UPI or cash, and seller confirms handover.</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Sticky Bidding Console */}
        <div className="area-panel">
          <BidPanel listing={listing} myBid={myBid} myMax={myMax} />
        </div>
      </div>
    </div>
  )
}

