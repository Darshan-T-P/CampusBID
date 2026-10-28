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
      setError(errorMessage(e))
      // Someone got in first: jump the box to the fresh minimum the server reports.
      if (e.code === 'too_low' && e.detail?.min_bid) setTouched(false)
      queryClient.invalidateQueries({ queryKey: ['listing', id] })
    },
  })

  function onSubmit(event) {
    event.preventDefault()
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
    <aside className="panel card" aria-label="Bidding">
      <div className="panel-top">
        <StatusBadge status={listing.status} />
        {isOpen && (
          <span key={listing.closes_at} className={listing.closes_at !== firstClose ? 'time-flash' : ''}>
            <Countdown closesAt={listing.closes_at} className="panel-countdown" />
          </span>
        )}
      </div>
      {isOpen && (
        <p className="muted small">
          Closes {new Date(listing.closes_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'medium' })}
          {listing.extension_count > 0 && (
            <span
              className="extended-chip"
              title="A bid in the last 30 seconds moves the closing time to 60 seconds after that bid"
            >
              <Icon name="clock" size={12} /> Extended{listing.extension_count > 1 ? ` ${listing.extension_count}×` : ''}
            </span>
          )}
        </p>
      )}
      {isOpen && listing.extension_count > 0 && (
        <p className="warn-box small" role="status">
          A late bid extended this auction. Bidding stays open until the countdown reaches zero.
        </p>
      )}

      <div className="panel-price">
        <span className="price-label">{hasBids ? 'Current bid' : 'Starting price'}</span>
        <strong key={shownPrice} className={`price-big ${shownPrice !== firstPrice ? 'price-flash' : ''}`} aria-live="polite">
          {formatRupees(shownPrice)}
        </strong>
        <span className="muted small">
          {listing.bid_count} {listing.bid_count === 1 ? 'bid' : 'bids'}
          {hasBids && <> · led by {listing.leading_bidder}</>}
        </span>
      </div>

      {myBid && isOpen && (
        <p className={myBid.is_leading ? 'success-box' : 'warn-box'} role="status">
          {myBid.is_leading
            ? `You're the highest bidder at ${formatRupees(myBid.my_highest_bid)}.`
            : `You've been outbid. Your best bid was ${formatRupees(myBid.my_highest_bid)}.`}
        </p>
      )}

      {!isOpen && (
        <>
          <p className="closed-message">{closedMessage(listing)}</p>
          {listing.outcome_note && <p className="muted small">{listing.outcome_note}</p>}
        </>
      )}

      {isOpen && timeUp && <p className="muted">This auction is closing…</p>}

      {isOpen && !timeUp && !isSignedIn && (
        <Link to="/login" state={{ from: location.pathname }} className="btn btn-primary btn-block">
          Sign in to bid
        </Link>
      )}
      {isOpen && !timeUp && isSignedIn && isSeller && (
        <p className="muted">This is your listing, so you can't bid on it.</p>
      )}
      {isOpen && !timeUp && isSignedIn && !isSeller && user && !user.is_verified && (
        <p className="warn-box">
          Verify your campus email to bid. <Link to="/verify">Enter your code</Link>
        </p>
      )}

      {isOpen && !timeUp && isSignedIn && !isSeller && user?.is_verified && isLeading && (
        <p className="muted small">You can bid again if someone outbids you.</p>
      )}

      {isOpen && !timeUp && isSignedIn && !isSeller && user?.is_verified && !isLeading && (
        <form onSubmit={onSubmit} className="bid-form" noValidate>
          <label htmlFor="bid-amount">Your bid (₹)</label>
          <div className="bid-row">
            <input
              id="bid-amount"
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
            <button className="btn btn-primary" disabled={placeBid.isPending}>
              {placeBid.isPending ? 'Placing…' : 'Place bid'}
            </button>
          </div>
          {minBid != null && (
            <div className="quick-bids">
              {[0, listing.min_increment, listing.min_increment * 2, listing.min_increment * 5].map((add, idx) => {
                const target = minBid + add
                return (
                  <button
                    key={idx}
                    type="button"
                    className="quick-bid-pill"
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
          )}
          <small id="bid-hint" className="muted">
            Minimum {formatRupees(minBid)} · bids go up by at least {formatRupees(listing.min_increment)}
          </small>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {notice && <p className="success-box" role="status">{notice}</p>}
        </form>
      )}

      {isOpen && !timeUp && isSignedIn && !isSeller && user?.is_verified && (
        <AutoBidBox listing={listing} myMax={myMax} leading={isLeading} />
      )}

      <div className="panel-seller-info">
        <p className="muted small panel-seller">
          Sold by <strong>{listing.seller.display_name}</strong>
          {(listing.seller.department || listing.seller.year_of_study) && (
            <span className="muted"> · {[yearLabel(listing.seller.year_of_study), listing.seller.department].filter(Boolean).join(', ')}</span>
          )}
          <span className="verified-student-chip" title="Verified campus student"><Icon name="shield" size={13} /> Verified</span>
        </p>
        {listing.handover_spot && (
          <p className="panel-spot-note">
            <Icon name="pin" size={14} /> Meet at <strong>{listing.handover_spot}</strong>
          </p>
        )}
      </div>
    </aside>
  )
}
