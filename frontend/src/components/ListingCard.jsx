import { Link } from 'react-router-dom'
import { mediaUrl } from '../api/client'
import { categoryLabel, conditionLabel, formatRupees } from '../lib/format'
import { Countdown } from './Countdown'

/** One auction in the browse grid. `listing` is a card from GET /listings. */
export function ListingCard({ listing }) {
  const hasBids = listing.bid_count > 0
  return (
    <Link to={`/listings/${listing.id}`} className="listing-card">
      <div className="thumb">
        {listing.thumbnail ? (
          <img src={mediaUrl(listing.thumbnail)} alt="" loading="lazy" />
        ) : (
          <div className="thumb-empty">No photo</div>
        )}
      </div>
      <div className="listing-body">
        <h3 className="listing-title">{listing.title}</h3>
        <div className="chips">
          <span className="chip">{categoryLabel(listing.category)}</span>
          <span className="chip">{conditionLabel(listing.condition)}</span>
        </div>
        <div className="price-row">
          <div>
            <span className="price-label">{hasBids ? 'Current bid' : 'Starting at'}</span>
            <strong className="price">{formatRupees(listing.price)}</strong>
          </div>
          <span className="muted small">
            {listing.bid_count} {listing.bid_count === 1 ? 'bid' : 'bids'}
          </span>
        </div>
        <div className="listing-meta">
          <Countdown closesAt={listing.closes_at} />
          <span className="muted small ellipsis">by {listing.seller_name}</span>
        </div>
      </div>
    </Link>
  )
}
