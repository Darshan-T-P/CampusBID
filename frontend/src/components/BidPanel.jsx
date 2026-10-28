import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { useNow } from '../hooks/useNow'
import { closedMessage, parseAmount, validateBid } from '../lib/bidding'
import { formatRupees } from '../lib/format'
import { Countdown } from './Countdown'
import { StatusBadge } from './StatusBadge'

/**
 * Everything on the right of the auction page: status, countdown, price, and the bid form.
 * What it shows depends on who is looking and what state the auction is in.
 *   listing  the ListingDetail from the API
 *   myBid    this user's row from /me/bids for this listing ({ my_highest_bid, is_leading }) or undefined
 */
export function BidPanel({ listing, myBid }) {
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
        {isOpen && <Countdown closesAt={listing.closes_at} className="panel-countdown" />}
      </div>
      {isOpen && (
        <p className="muted small">Closes {new Date(listing.closes_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</p>
      )}

      <div className="panel-price">
        <span className="price-label">{hasBids ? 'Current bid' : 'Starting price'}</span>
        <strong className="price-big">{formatRupees(listing.current_price ?? listing.starting_price)}</strong>
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

      <p className="muted small panel-seller">
        Sold by <strong>{listing.seller.display_name}</strong>
      </p>
    </aside>
  )
}
