import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, mediaUrl } from '../api/client'
import { errorMessage } from '../api/errors'
import { Countdown } from '../components/Countdown'
import { SellerActions } from '../components/SellerActions'
import { StatusBadge } from '../components/StatusBadge'
import { formatRupees } from '../lib/format'
import { groupListings } from '../lib/sale'

const LIMIT = 50

function Row({ listing, notice, onNotice }) {
  // Once an auction has a winner the seller needs to know who: that is in the detail, not the card.
  const hasWinner = listing.status === 'pending_approval' || listing.status === 'reserved'
  const detail = useQuery({
    queryKey: ['listing', String(listing.id)],
    queryFn: () => api(`/listings/${listing.id}`),
    enabled: hasWinner,
  })
  const d = detail.data

  return (
    <li className="row-card">
      <Link to={`/listings/${listing.id}`} className="row-thumb" aria-hidden="true" tabIndex={-1}>
        {listing.thumbnail ? <img src={mediaUrl(listing.thumbnail)} alt="" loading="lazy" /> : <span>No photo</span>}
      </Link>
      <div className="row-main">
        <div className="row-title">
          <Link to={`/listings/${listing.id}`}>{listing.title}</Link>
          <StatusBadge status={listing.status} />
        </div>
        <p className="muted small">
          {listing.bid_count > 0 ? `Highest bid ${formatRupees(listing.price)}` : `Starting at ${formatRupees(listing.price)}`}
          {' · '}
          {listing.bid_count} {listing.bid_count === 1 ? 'bid' : 'bids'}
          {listing.status === 'active' && (
            <>
              {' · '}
              <Countdown closesAt={listing.closes_at} />
            </>
          )}
        </p>
        {hasWinner && d?.leading_bidder && (
          <p className="winner-line">
            {listing.status === 'pending_approval' ? 'Winner' : 'Reserved for'}: <strong>{d.leading_bidder}</strong> at {formatRupees(d.current_price)}
          </p>
        )}
        {!hasWinner && d?.outcome_note && <p className="muted small">{d.outcome_note}</p>}
        <SellerActions listing={listing} notice={notice} onNotice={onNotice} />
      </div>
    </li>
  )
}

export function MyListings() {
  // One message per listing, kept here so it survives the listing moving between sections.
  const [notices, setNotices] = useState({})
  const setNotice = (id) => (notice) => setNotices((n) => ({ ...n, [id]: notice }))

  const query = useQuery({
    queryKey: ['my-listings'],
    queryFn: () => api(`/me/listings?limit=${LIMIT}`),
    refetchInterval: 10_000, // a listing can end (and need a decision) while this page is open
  })

  if (query.isPending) return <p className="muted center">Loading your listings…</p>
  if (query.isError) {
    return (
      <p className="error" role="alert">
        {errorMessage(query.error)}{' '}
        <button type="button" className="link-button" onClick={() => query.refetch()}>
          Try again
        </button>
      </p>
    )
  }

  const { items, total } = query.data
  const groups = groupListings(items)

  return (
    <section>
      <div className="page-head">
        <h1>My listings</h1>
        <Link to="/sell" className="btn btn-primary">
          Sell an item
        </Link>
      </div>

      {items.length === 0 ? (
        <div className="empty card">
          <p>You haven't listed anything yet.</p>
          <Link to="/sell" className="btn btn-primary">
            List your first item
          </Link>
        </div>
      ) : (
        groups.map((group) => (
          <div key={group.key} className="group">
            <h2>
              {group.title} <span className="muted">({group.items.length})</span>
            </h2>
            {group.hint && <p className="muted small">{group.hint}</p>}
            <ul className="rows">
              {group.items.map((listing) => (
                <Row key={listing.id} listing={listing} notice={notices[listing.id]} onNotice={setNotice(listing.id)} />
              ))}
            </ul>
          </div>
        ))
      )}
      {total > LIMIT && <p className="muted small">Showing your {LIMIT} most recent of {total} listings.</p>}
    </section>
  )
}
