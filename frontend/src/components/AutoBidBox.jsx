import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { parseAmount, parseRaise } from '../lib/bidding'
import { APP_NAME } from '../lib/brand'
import { formatRupees } from '../lib/format'

/**
 * "Bid for me up to this much." The app places bids on the buyer's behalf, only as much as needed to
 * keep them in front, and never past the maximum. Maximums are public, which the box says plainly.
 *   listing  the ListingDetail
 *   myMax    this buyer's current maximum on this auction, or null
 *   myStep   how much they chose each automatic bid should raise the price by, or null (the auction's minimum raise)
 *   leading  whether this buyer currently has the highest bid
 */
export function AutoBidBox({ listing, myMax, myStep = null, leading }) {
  const queryClient = useQueryClient()
  const id = String(listing.id)
  const [editing, setEditing] = useState(false)
  const [typed, setTyped] = useState('')
  const [typedStep, setTypedStep] = useState('')
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  // A leader only has to cover their own price; anyone else has to be able to beat the current one.
  const floor = leading ? listing.current_price : listing.min_next_bid

  const refresh = () => {
    for (const key of [['auto-bids', id], ['my-auto-bids'], ['bids', id], ['my-bids'], ['listings']]) {
      queryClient.invalidateQueries({ queryKey: key })
    }
  }

  const minRaise = listing.min_increment

  const save = useMutation({
    // `step` is always sent: a number is the raise they chose, null means "the auction's minimum" (and resets an old choice).
    mutationFn: ({ amount, step }) => api(`/listings/${id}/auto-bid`, { method: 'PUT', body: { max_amount: amount, step } }),
    onSuccess: (result) => {
      queryClient.setQueryData(['listing', id], result.listing) // the app may already have bid for them
      refresh()
      setEditing(false)
      setTyped('')
      setTypedStep('')
      setError(null)
      setNotice(
        `Limit set to ${formatRupees(result.auto_bid.max_amount)}, raising ${
          result.auto_bid.step ? `${formatRupees(result.auto_bid.step)} each time` : `by the minimum raise (${formatRupees(minRaise)})`
        }.`,
      )
    },
    onError: (e) => {
      setNotice(null)
      if (e.code === 'too_low') {
        const freshMin = e.detail?.min_bid || floor
        setError(`A higher bid was just placed! Your maximum must be at least ${freshMin ? formatRupees(freshMin) : 'higher'}.`)
      } else if (e.code === 'closed') {
        setError('This auction has closed. No further maximums can be set.')
      } else {
        setError(errorMessage(e))
      }
      queryClient.invalidateQueries({ queryKey: ['listing', id] })
    },
  })

  const remove = useMutation({
    mutationFn: () => api(`/listings/${id}/auto-bid`, { method: 'DELETE' }),
    onSuccess: () => {
      refresh()
      setEditing(false)
      setError(null)
      setNotice('Maximum removed. Bids already placed stand.')
    },
    onError: (e) => setError(errorMessage(e)),
  })

  function onSubmit(event) {
    event.preventDefault()
    setNotice(null)
    const amount = parseAmount(typed)
    if (amount === null) return setError('Enter a whole number of rupees')
    if (floor != null && amount < floor) return setError(`Your maximum must be at least ${formatRupees(floor)}`)
    const raise = parseRaise(typedStep, minRaise)
    if (raise.error) return setError(raise.error)
    setError(null)
    save.mutate({ amount, step: raise.value })
  }

  const showForm = myMax == null || editing

  return (
    <section className="auto-box" aria-label="Automatic bidding">
      <div className="auto-head">
        <strong>Automatic Bidding</strong>
        <span className="muted small">
          Set your maximum limit and {APP_NAME} bids for you automatically to keep you in the lead. Each automatic bid raises the price
          by the auction's minimum raise ({formatRupees(minRaise)}) unless you choose a bigger raise. Limits are public.
        </span>
      </div>

      {myMax != null && !editing && (
        <p className="auto-current">
          Your limit: <strong>{formatRupees(myMax)}</strong>
          <span className="muted small"> · raises {myStep ? formatRupees(myStep) : `${formatRupees(minRaise)} (the minimum)`} each time</span>
          <span className="auto-actions">
            <button type="button" className="link-button" onClick={() => { setEditing(true); setTyped(String(myMax)); setTypedStep(myStep ? String(myStep) : ''); setNotice(null) }}>
              Change
            </button>
            <button type="button" className="link-button" disabled={remove.isPending} onClick={() => remove.mutate()}>
              Remove
            </button>
          </span>
        </p>
      )}

      {showForm && (
        <form onSubmit={onSubmit} className="auto-form" noValidate>
          <label htmlFor="auto-max" className="sr-only">Your maximum limit (₹)</label>
          <div className="bid-row">
            <input
              id="auto-max"
              inputMode="numeric"
              autoComplete="off"
              placeholder={floor != null ? `At least ${floor}` : 'Maximum limit in ₹'}
              value={typed}
              onChange={(e) => { setTyped(e.target.value); setError(null) }}
              aria-invalid={error ? 'true' : undefined}
            />
            <button className="btn btn-ghost" disabled={save.isPending}>
              {save.isPending ? 'Saving…' : myMax == null ? 'Set limit' : 'Update limit'}
            </button>
          </div>
          <div className="auto-step-row">
            <label htmlFor="auto-step">Raise by (₹) each time</label>
            <input
              id="auto-step"
              inputMode="numeric"
              autoComplete="off"
              placeholder={`${minRaise} (the minimum)`}
              value={typedStep}
              onChange={(e) => { setTypedStep(e.target.value); setError(null) }}
            />
            <small className="muted">Optional. A bigger raise jumps ahead faster but costs you more. It can't be below {formatRupees(minRaise)}.</small>
          </div>
          {editing && (
            <button type="button" className="link-button small" onClick={() => { setEditing(false); setError(null) }}>
              Cancel
            </button>
          )}
        </form>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="success-box" role="status">{notice}</p>}
    </section>
  )
}
