import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { ApiError, api } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { AutoBidList } from '../components/AutoBidList'
import { BidHistory } from '../components/BidHistory'
import { BidPanel } from '../components/BidPanel'
import { Icon } from '../components/Icon'
import { ImageGallery } from '../components/ImageGallery'
import { categoryLabel, conditionLabel } from '../lib/format'

const LIVE_MS = 2500 // while the auction is open, so two browsers see each other's bids almost at once
const IDLE_MS = 20_000 // once it has ended, nothing changes quickly

export function ListingPage() {
  const { id } = useParams()
  const location = useLocation()
  const { isSignedIn, user } = useAuth()
  const queryClient = useQueryClient()

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

  // Automatic bidding: my own maximum, and everyone's (public). Maximums can change without a bid being
  // placed, so while the auction is open these are checked a little more often than the history.
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

  if (listingQuery.isPending) return <p className="muted center">Loading auction…</p>

  if (listingQuery.isError) {
    const notFound = listingQuery.error instanceof ApiError && listingQuery.error.status === 404
    return (
      <section className="center">
        <h1>{notFound ? "This auction doesn't exist" : "Couldn't load this auction"}</h1>
        {!notFound && <p className="error">{errorMessage(listingQuery.error)}</p>}
        <p>
          {!notFound && (
            <button type="button" className="btn btn-ghost" onClick={() => listingQuery.refetch()}>
              Try again
            </button>
          )}{' '}
          <Link to="/">← Back to browsing</Link>
        </p>
      </section>
    )
  }

  return (
    <section>
      {location.state?.saved && (
        <p className="success-box" role="status">
          Changes saved.
        </p>
      )}
      {location.state?.published && (
        <p className="success-box" role="status">
          Your listing is live! Students can start bidding now.
        </p>
      )}
      <p className="crumbs">
        <Link to="/">← All auctions</Link>
      </p>
      <div className="page-head">
        <h1 className="listing-h1">{listing.title}</h1>
        {isOpen && user?.id === listing.seller.id && (
          <Link to={`/listings/${listing.id}/edit`} className="btn btn-ghost btn-sm">
            Edit listing
          </Link>
        )}
      </div>
      <div className="chips">
        <span className="chip">{categoryLabel(listing.category)}</span>
        <span className="chip">{conditionLabel(listing.condition)}</span>
        {!isOpen && <span className="chip">Bidding closed</span>}
      </div>

      {/* Three areas so phones get photos -> bid panel -> description, while desktop keeps the panel beside them. */}
      <div className="detail-grid">
        <div className="area-gallery">
          <ImageGallery images={listing.images} title={listing.title} />
        </div>
        <div className="area-panel">
          <BidPanel listing={listing} myBid={myBid} myMax={myMax} />
        </div>
        <div className="area-about">
          <h2>About this item</h2>
          <p className="description">{listing.description || 'The seller has not added a description.'}</p>
          {listing.edited_at && (
            <p className="muted small edited-note">
              Edited {new Date(listing.edited_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
            </p>
          )}

          {listing.handover_spot && (
            <div className="handover-spot-card">
              <div className="handover-spot-icon"><Icon name="pin" size={22} /></div>
              <div className="handover-spot-body">
                <strong className="handover-spot-title">Campus Handover Spot: {listing.handover_spot}</strong>
                <p className="handover-spot-desc">
                  Meet in person on campus during daylight. Always test and inspect the item before paying via UPI / cash.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      <h2 className="history-title">Bid history {listing.bid_count > 0 && <span className="muted">({listing.bid_count})</span>}</h2>
      {bidsQuery.isPending ? <p className="muted">Loading bids…</p> : <BidHistory bids={bidsQuery.data ?? []} />}

      <h2 className="history-title">
        Automatic maximums {autoBidsQuery.data?.length > 0 && <span className="muted">({autoBidsQuery.data.length})</span>}
      </h2>
      <p className="muted small">Visible to everyone. The app only bids for someone as much as needed to keep them in front.</p>
      <AutoBidList autoBids={autoBidsQuery.data ?? []} />
    </section>
  )
}
