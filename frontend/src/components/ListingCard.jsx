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
          <img src={mediaUrl(listing.thumbnail)} alt={listing.title} loading="lazy" />
        ) : (
          <div className="thumb-empty">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
              <circle cx="9" cy="9" r="2"/>
              <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
            </svg>
            <span>No photo</span>
          </div>
        )}
        <span className="thumb-category">{categoryLabel(listing.category)}</span>
      </div>
      <div className="listing-body">
        <h3 className="listing-title">{listing.title}</h3>
        <div className="chips">
          <span className="chip">{conditionLabel(listing.condition)}</span>
          <span className="seller-by">by {listing.seller_name}</span>
        </div>
        <div className="price-row">
          <div>
            <span className="price-label">{hasBids ? 'Current bid' : 'Starting price'}</span>
            <strong className="price">{formatRupees(listing.price)}</strong>
          </div>
          <span className="bid-count-pill">
            {listing.bid_count} {listing.bid_count === 1 ? 'bid' : 'bids'}
          </span>
        </div>
        <div className="listing-meta">
          <Countdown closesAt={listing.closes_at} />
        </div>
      </div>
    </Link>
  )
}
