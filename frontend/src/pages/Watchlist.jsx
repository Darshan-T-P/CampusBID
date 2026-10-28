import { Link } from 'react-router-dom'
import { mediaUrl } from '../api/client'
import { errorMessage } from '../api/errors'
import { Countdown } from '../components/Countdown'
import { StatusBadge } from '../components/StatusBadge'
import { WatchButton } from '../components/WatchButton'
import { useWatchlist } from '../hooks/useWatchlist'
import { formatRupees } from '../lib/format'

export function Watchlist() {
  const { query, items } = useWatchlist({ poll: true })

  if (query.isPending) return <p className="muted center">Loading your watchlist…</p>
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

  const open = items.filter((c) => c.status === 'active')
  const ended = items.filter((c) => c.status !== 'active')

  return (
    <section>
      <h1>Watchlist</h1>
      <p className="muted">Auctions you saved. You'll get a reminder an hour and five minutes before each one closes, and be told how it ended.</p>
      {items.length === 0 ? (
        <div className="empty card">
          <p>Nothing saved yet. Use the bookmark on any auction to keep an eye on it.</p>
          <Link to="/" className="btn btn-primary">
            Browse auctions
          </Link>
        </div>
      ) : (
        [
          ['Open now', open],
          ['Ended', ended],
        ]
          .filter(([, group]) => group.length > 0)
          .map(([title, group]) => (
            <div key={title} className="group">
              <h2>
                {title} <span className="muted">({group.length})</span>
              </h2>
              <ul className="rows">
                {group.map((listing) => (
                  <li key={listing.id} className="row-card">
                    <Link to={`/listings/${listing.id}`} className="row-thumb" aria-hidden="true" tabIndex={-1}>
                      {listing.thumbnail ? <img src={mediaUrl(listing.thumbnail)} alt="" loading="lazy" /> : <span>No photo</span>}
                    </Link>
                    <div className="row-main">
                      <div className="row-title">
                        <Link to={`/listings/${listing.id}`}>{listing.title}</Link>
                        <StatusBadge status={listing.status} />
                      </div>
                      <p className="muted small">
                        {listing.bid_count > 0 ? 'Current bid' : 'Starting price'} <strong>{formatRupees(listing.price)}</strong> · {listing.bid_count}{' '}
                        {listing.bid_count === 1 ? 'bid' : 'bids'}
                      </p>
                      {listing.status === 'active' && (
                        <p className="muted small">
                          <Countdown closesAt={listing.closes_at} /> · <Link to={`/listings/${listing.id}`}>Bid</Link>
                        </p>
                      )}
                    </div>
                    <WatchButton listingId={listing.id} sellerId={listing.seller_id} />
                  </li>
                ))}
              </ul>
            </div>
          ))
      )}
    </section>
  )
}
