import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { useNow } from '../hooks/useNow'
import { closedMessage, parseAmount, validateBid } from '../lib/bidding'
import { formatRupees, yearLabel } from '../lib/format'
import { AutoBidBox } from './AutoBidBox'
import { Countdown } from './Countdown'
import { Icon } from './Icon'
import { StatusBadge } from './StatusBadge'

/**
 * Everything on the right of the auction page: status, countdown, price, and the bid form.
 * What it shows depends on who is looking and what state the auction is in.
 *   listing  the ListingDetail from the API
 *   myBid    this user's row from /me/bids for this listing ({ my_highest_bid, is_leading }) or undefined
 *   myMax    this user's automatic-bidding maximum on this auction, or null
 */
export function BidPanel({ listing, myBid, myMax = null }) {
  const { user, isSignedIn } = useAuth()
  const location = useLocation()
  const queryClient = useQueryClient()
  const now = useNow()

  const id = String(listing.id)
  const isOpen = listing.status === 'active'
  const timeUp = Date.parse(listing.closes_at) - now <= 0
  const isSeller = user != null && user.id === listing.seller.id
  const minBid = listing.min_next_bid
  const isLeading = Boolean(myBid?.is_leading)
  const shownPrice = listing.current_price ?? listing.starting_price
  const [firstPrice] = useState(shownPrice) // the price when the page opened: only LATER changes flash
  const [firstClose] = useState(listing.closes_at) // likewise: only a LATER change to the closing time flashes

  const [typed, setTyped] = useState('')
  const [touched, setTouched] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  // Until the bidder types their own amount, the box shows the current minimum. It is derived
  // on every render, so if somebody outbids them while they're reading, the suggestion moves up.
  const text = touched ? typed : minBid != null ? String(minBid) : ''

  const placeBid = useMutation({
    mutationFn: (amount) => api(`/listings/${id}/bids`, { method: 'POST', body: { amount } }),
    onSuccess: (result) => {
      // The response already holds the listing as it now stands: show it at once, no waiting for a poll.
      queryClient.setQueryData(['listing', id], result.listing)
      queryClient.invalidateQueries({ queryKey: ['bids', id] })
      queryClient.invalidateQueries({ queryKey: ['my-bids'] })
      queryClient.invalidateQueries({ queryKey: ['listings'] })
      setTouched(false)
      setError(null)
      setNotice(`Bid placed: ${formatRupees(result.bid.amount)}. You're the highest bidder.`)
    },
    onError: (e) => {
      setNotice(null)
      if (e.code === 'too_low') {
        const freshMin = e.detail?.min_bid || minBid
        setError(`Another student placed a bid just before you! The next minimum bid is ${freshMin ? formatRupees(freshMin) : 'higher'}.`)
        setTouched(false)
        if (freshMin) setTyped(String(freshMin))
      } else if (e.code === 'closed') {
        setError('This auction has closed. No further bids can be accepted.')
      } else if (e.code === 'already_leading') {
        setError('You are already the highest bidder!')
      } else {
        setError(errorMessage(e))
      }
      queryClient.invalidateQueries({ queryKey: ['listing', id] })
    },
  })

  function onSubmit(event) {
    event.preventDefault()
    if (placeBid.isPending) return
    setNotice(null)
    const problem = validateBid(text, minBid)
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    placeBid.mutate(parseAmount(text))
  }

  const hasBids = listing.bid_count > 0

  return (
    <aside className="panel card panel-console" aria-label="Bidding Console">
      {/* Top Status & Live Countdown Bar */}
      <div className="panel-status-header">
        <StatusBadge status={listing.status} />
        {isOpen && (
          <div key={listing.closes_at} className={`panel-countdown-wrap ${listing.closes_at !== firstClose ? 'time-flash' : ''}`}>
            <Countdown closesAt={listing.closes_at} className="panel-countdown-tag" />
          </div>
        )}
      </div>

      {isOpen && (
        <div className="panel-closing-row">
          <Icon name="clock" size={13} className="text-muted" />
          <span className="muted small">
            Closes {new Date(listing.closes_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
          </span>
          {listing.extension_count > 0 && (
            <span
              className="extended-chip"
              title="A bid in the last 30 seconds moves the closing time to 60 seconds after that bid"
            >
              Extended{listing.extension_count > 1 ? ` ${listing.extension_count}×` : ''}
            </span>
          )}
        </div>
      )}

      {isOpen && listing.extension_count > 0 && (
        <div className="warn-box small" role="status">
          <Icon name="zap" size={14} /> Late bid extension active. Timer resets to 60s on last-minute bids.
        </div>
      )}

      {/* High-Impact Price Hero */}
      <div className="panel-price-hero">
        <div className="price-hero-label">
          {hasBids ? 'Current highest bid' : 'Starting price'}
        </div>
        <div className="price-hero-main">
          <strong key={shownPrice} className={`price-giant ${shownPrice !== firstPrice ? 'price-flash' : ''}`} aria-live="polite">
            {formatRupees(shownPrice)}
          </strong>
        </div>
        <div className="price-hero-sub">
          <span className="bid-count-badge">
            <Icon name="trend" size={12} /> {listing.bid_count} {listing.bid_count === 1 ? 'bid' : 'bids'}
          </span>
          {hasBids && (
            <span className="leader-badge">
              Leading: <strong>{listing.leading_bidder}</strong>
            </span>
          )}
        </div>
      </div>

      {/* User Standing Callout Banner */}
      {myBid && isOpen && (
        <div className={`standing-banner ${myBid.is_leading ? 'standing-banner-winning' : 'standing-banner-outbid'}`} role="status">
          {myBid.is_leading ? (
            <>
              <Icon name="award" size={18} className="standing-icon" />
              <div className="standing-text">
                <strong>You are currently winning!</strong>
                <span>Highest bid placed: {formatRupees(myBid.my_highest_bid)}</span>
              </div>
            </>
          ) : (
            <>
              <Icon name="zap" size={18} className="standing-icon" />
              <div className="standing-text">
                <strong>You've been outbid!</strong>
                <span>Your best was {formatRupees(myBid.my_highest_bid)}. Re-bid to take the lead.</span>
              </div>
            </>
          )}
        </div>
      )}

      {!isOpen && (
        <div className="panel-closed-box">
          <p className="closed-message">{closedMessage(listing)}</p>
          {listing.outcome_note && <p className="muted small">{listing.outcome_note}</p>}
        </div>
      )}

      {isOpen && timeUp && <p className="muted center">This auction is closing…</p>}

      {isOpen && !timeUp && !isSignedIn && (
        <div className="panel-auth-cta">
          <p className="muted small center">Sign in with your campus email to place a bid</p>
          <Link to="/login" state={{ from: location.pathname }} className="btn btn-primary btn-block">
            Sign in to bid
          </Link>
        </div>
      )}

      {isOpen && !timeUp && isSignedIn && isSeller && (
        <div className="panel-seller-note">
          <Icon name="shield" size={16} />
          <span>This is your listing. As seller, you cannot bid on your own item.</span>
        </div>
      )}

      {isOpen && !timeUp && isSignedIn && !isSeller && user && !user.is_verified && (
        <div className="warn-box">
          Verify your campus email to bid. <Link to="/verify">Enter your verification code</Link>
        </div>
      )}

      {isOpen && !timeUp && isSignedIn && !isSeller && user?.is_verified && isLeading && (
        <p className="muted small center lead-note">
          You currently hold the highest bid. You can bid again if outbid.
        </p>
      )}

      {/* Bidding Form */}
      {isOpen && !timeUp && isSignedIn && !isSeller && user?.is_verified && !isLeading && (
        <form onSubmit={onSubmit} className="bid-form-modern" noValidate>
          <div className="bid-input-group">
            <label htmlFor="bid-amount" className="bid-input-label">
              <span>Your Bid</span>
              <span className="bid-min-hint">Min {formatRupees(minBid)}</span>
            </label>
            <div className="currency-input-wrap">
              <span className="currency-prefix">₹</span>
              <input
                id="bid-amount"
                className="bid-input"
                inputMode="numeric"
                autoComplete="off"
                value={text}
                onChange={(e) => {
                  setTyped(e.target.value)
                  setTouched(true)
                  setError(null)
                }}
                aria-describedby="bid-hint"
                aria-invalid={error ? 'true' : undefined}
              />
              <button className="btn btn-primary btn-bid-submit" disabled={placeBid.isPending}>
                {placeBid.isPending ? 'Placing…' : 'Place Bid'}
              </button>
            </div>
          </div>

          {/* Quick-Bid Preset Increment Chips */}
          {minBid != null && (
            <div className="quick-bids-row">
              <span className="quick-bids-label">Quick select:</span>
              <div className="quick-bids-chips">
                {[0, listing.min_increment, listing.min_increment * 2, listing.min_increment * 5].map((add, idx) => {
                  const target = minBid + add
                  return (
                    <button
                      key={idx}
                      type="button"
                      className="quick-chip"
                      onClick={() => {
                        setTyped(String(target))
                        setTouched(true)
                        setError(null)
                      }}
                    >
                      {add === 0 ? `Min ₹${target}` : `+₹${add}`}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          <p id="bid-hint" className="bid-increment-hint">
            Bids must increase by at least {formatRupees(listing.min_increment)}
          </p>

          {error && (
            <div className="error-box" role="alert">
              <Icon name="x" size={14} /> {error}
            </div>
          )}
          {notice && (
            <div className="success-banner" role="status">
              <Icon name="check" size={14} /> {notice}
            </div>
          )}
        </form>
      )}

      {/* Automatic Proxy Bidding Box */}
      {isOpen && !timeUp && isSignedIn && !isSeller && user?.is_verified && (
        <AutoBidBox listing={listing} myMax={myMax} leading={isLeading} />
      )}

      {/* Footer Info */}
      <div className="panel-footer-meta">
        <div className="footer-seller-row">
          <div className="footer-seller-text">
            Listed by <strong>{listing.seller.display_name}</strong>
            {(listing.seller.department || listing.seller.year_of_study) && (
              <span className="muted small"> · {[yearLabel(listing.seller.year_of_study), listing.seller.department].filter(Boolean).join(', ')}</span>
            )}
          </div>
          <span className="verified-student-chip" title="Verified campus student">
            <Icon name="shield" size={12} /> Verified
          </span>
        </div>
        {listing.handover_spot && (
          <div className="footer-spot-row">
            <Icon name="pin" size={14} />
            <span>Meet at <strong>{listing.handover_spot}</strong></span>
          </div>
        )}
      </div>
    </aside>
  )
}

