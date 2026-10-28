import { Link } from 'react-router-dom'
import { mediaUrl } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { categoryLabel, conditionLabel, formatRupees } from '../lib/format'
import { useNow } from '../hooks/useNow'
import { Countdown } from './Countdown'
import { Icon } from './Icon'
import { WatchButton } from './WatchButton'

/** One auction in the browse grid. `listing` is a card from GET /listings. */
export function ListingCard({ listing }) {
  const hasBids = listing.bid_count > 0
  const msLeft = Date.parse(listing.closes_at) - useNow()
  const endingSoon = msLeft > 0 && msLeft < 60 * 60 * 1000
  const hot = listing.bid_count >= 4
  const { user } = useAuth()
  const isMine = user != null && user.id === listing.seller_id // your own auction: tagged, and you can't bid on or save it
  return (
    <div className="card-wrap">
    <Link to={`/listings/${listing.id}`} className={`listing-card ${isMine ? 'listing-card-mine' : ''}`}>
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
        {isMine && (
          <span className="thumb-mine">
            <Icon name="user" size={12} /> Your listing
          </span>
        )}
        {(endingSoon || hot) && (
          <span className="thumb-badges">
            {endingSoon && <span className="thumb-badge thumb-badge-soon"><Icon name="clock" size={12} /> Ending soon</span>}
            {hot && <span className="thumb-badge thumb-badge-hot"><Icon name="trend" size={12} /> {listing.bid_count} bids</span>}
          </span>
        )}
      </div>
      <div className="listing-body">
        <h3 className="listing-title">{listing.title}</h3>
        <div className="chips">
          <span className="chip">{conditionLabel(listing.condition)}</span>
          <span className="seller-by">by {isMine ? 'you' : listing.seller_name}</span>
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
          {listing.watchers > 0 && (
            <span className="watching-count" title="Students who saved this auction">
              <Icon name="bookmark" size={12} filled /> {listing.watchers} watching
            </span>
          )}
          {listing.handover_spot && (
            <span className="card-handover-spot" title={`Campus Handover Spot: ${listing.handover_spot}`}>
              <Icon name="pin" size={13} /> {listing.handover_spot}
            </span>
          )}
        </div>
      </div>
    </Link>
    {listing.status === 'active' && <WatchButton listingId={listing.id} sellerId={listing.seller_id} variant="icon" />}
    </div>
  )
}
