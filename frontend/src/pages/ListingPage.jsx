import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { AutoBidList } from '../components/AutoBidList'
import { BidHistory } from '../components/BidHistory'
import { BidPanel } from '../components/BidPanel'
import { ContactCard } from '../components/ContactCard'
import { ListingQA } from '../components/ListingQA'
import { WatchButton } from '../components/WatchButton'
import { Icon } from '../components/Icon'
import { ImageGallery } from '../components/ImageGallery'
import { useAuctionStream } from '../hooks/useAuctionStream'
import { categoryLabel, conditionLabel, formatRupees, yearLabel } from '../lib/format'
import { memberSince } from '../lib/profileForm'

const LIVE_MS = 2500 // fallback when real-time push is connecting
const IDLE_MS = 20_000 // once it has ended, nothing changes quickly

export function ListingPage() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { isSignedIn, user } = useAuth()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('overview') // 'overview' | 'bids' | 'autobids' | 'safety'

  const deleteMutation = useMutation({
    mutationFn: () => api(`/listings/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['listings'] })
      queryClient.invalidateQueries({ queryKey: ['my-listings'] })
      navigate('/my-listings')
    },
  })

  const cancelMutation = useMutation({
    mutationFn: () => api(`/listings/${id}/cancel`, { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['listing', id] })
      queryClient.invalidateQueries({ queryKey: ['listings'] })
      queryClient.invalidateQueries({ queryKey: ['my-listings'] })
    },
  })

  // Connect real-time Server-Sent Events (SSE) push stream
  const { isConnected: isRealtime } = useAuctionStream(id, user?.id)

  // Real-time SSE handles immediate pushes; background polling is relaxed to an infrequent fallback.
  const listingQuery = useQuery({
    queryKey: ['listing', id],
    queryFn: () => api(`/listings/${id}`),
    refetchInterval: (query) => (query.state.data?.status === 'active' ? (isRealtime ? 60_000 : LIVE_MS) : IDLE_MS),
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
      queryClient.invalidateQueries({ queryKey: ['my-bids'] })
      queryClient.invalidateQueries({ queryKey: ['auto-bids', id] })
    }
    lastMarker.current = marker
  }, [marker, id, queryClient])

  useEffect(() => {
    if (listing) document.title = `${listing.title} · CampusBid`
    return () => {
      document.title = 'CampusBid'
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
        {user?.id === listing.seller.id && (
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            {isOpen && (
              <Link to={`/listings/${listing.id}/edit`} className="btn btn-ghost btn-sm">
                Edit listing
              </Link>
            )}
            {isOpen && listing.bid_count > 0 && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ color: 'var(--danger)' }}
                disabled={cancelMutation.isPending}
                onClick={() => {
                  if (window.confirm('Cancel this auction? Active bidders will be notified.')) {
                    cancelMutation.mutate()
                  }
                }}
              >
                {cancelMutation.isPending ? 'Cancelling…' : 'Cancel auction'}
              </button>
            )}
            {listing.bid_count === 0 && (listing.status === 'active' || listing.status === 'cancelled' || listing.status === 'unsold') && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ color: 'var(--danger)' }}
                disabled={deleteMutation.isPending}
                onClick={() => {
                  if (window.confirm('Permanently delete this listing? This action cannot be undone.')) {
                    deleteMutation.mutate()
                  }
                }}
              >
                {deleteMutation.isPending ? 'Deleting…' : 'Delete listing'}
              </button>
            )}
          </div>
        )}
        {isOpen && <WatchButton listingId={listing.id} sellerId={listing.seller.id} />}
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
            <span
              className="listing-badge listing-badge-live"
              title={isRealtime ? 'Connected to live Server-Sent Events push stream' : 'Live Auction'}
            >
              <span className="pulse-dot" /> {isRealtime ? 'Live Realtime' : 'Live Auction'}
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
                    <div className="seller-top">
                      <div className="seller-avatar">{sellerInitials}</div>
                      <div className="seller-details">
                        <div className="seller-name-row">
                          <strong className="seller-name">{listing.seller.display_name}</strong>
                          <span className="verified-badge-chip">
                            <Icon name="shield" size={13} /> Verified Student
                          </span>
                        </div>
                        <p className="seller-meta">
                          {[yearLabel(listing.seller.year_of_study), listing.seller.department].filter(Boolean).join(' · ') || 'Year and department not shared'}
                        </p>
                      </div>
                    </div>
                    <dl className="seller-stats">
                      <div><dt>Items sold</dt><dd>{listing.seller.items_sold}</dd></div>
                      <div><dt>Listed</dt><dd>{listing.seller.listed}</dd></div>
                      <div><dt>Open now</dt><dd>{listing.seller.open_now}</dd></div>
                      <div><dt>Member since</dt><dd>{listing.seller.member_since ? memberSince(listing.seller.member_since) : '-'}</dd></div>
                    </dl>
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
                      Automatic Bids {autoBidsQuery.data?.length > 0 && <span className="muted">({autoBidsQuery.data.length})</span>}
                    </h3>
                  </div>
                  <p className="muted small info-banner">
                    <Icon name="shield" size={14} /> Maximum limits are transparent and visible to all students. The system only bids on your behalf as much as necessary to maintain the lead.
                  </p>
                  <AutoBidList autoBids={autoBidsQuery.data ?? []} />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Sticky Bidding Console, Handover Security, and Q&A */}
        <div className="area-panel">
          <BidPanel listing={listing} myBid={myBid} myMax={myMax} />
          {isSignedIn && listing.status === 'reserved' && <ContactCard listingId={listing.id} />}

          {/* Handover & Security Protocol Card */}
          <div className="handover-sec-card card">
            <div className="handover-sec-header">
              <span className="handover-sec-icon">
                <Icon name="shield" size={18} />
              </span>
              <div>
                <h3 className="handover-sec-title">Handover & Safety Protocol</h3>
                <span className="muted small">Safe in-person campus handover</span>
              </div>
            </div>

            {listing.handover_spot && (
              <div className="handover-spot-banner">
                <Icon name="pin" size={15} />
                <div className="handover-spot-info">
                  <span className="handover-spot-sub">Designated Meetup Spot</span>
                  <strong className="handover-spot-val">{listing.handover_spot}</strong>
                </div>
              </div>
            )}

            <ul className="handover-sec-checklist">
              <li>
                <span className="checklist-bullet">01</span>
                <div>
                  <strong>Verified Students Only</strong>
                  <p>Authenticated campus domain email addresses for both buyer and seller.</p>
                </div>
              </li>
              <li>
                <span className="checklist-bullet">02</span>
                <div>
                  <strong>Daylight Public Exchange</strong>
                  <p>Meet in open, populated campus areas (Library gate, Canteen, Quadrangle).</p>
                </div>
              </li>
              <li>
                <span className="checklist-bullet">03</span>
                <div>
                  <strong>Inspect First, Settle After</strong>
                  <p>Test item condition and functionality before making any payment.</p>
                </div>
              </li>
              <li>
                <span className="checklist-bullet">04</span>
                <div>
                  <strong>Direct Peer-to-Peer</strong>
                  <p>Zero platform fees. Pay directly via UPI or cash upon confirmed handover.</p>
                </div>
              </li>
            </ul>
          </div>

          {/* Questions & Answers */}
          <ListingQA listing={listing} />
        </div>
      </div>
    </div>
  )
}

