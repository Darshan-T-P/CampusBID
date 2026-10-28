import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { parseAmount } from '../lib/bidding'
import { formatRupees } from '../lib/format'

/**
 * "Bid for me up to this much." The app places bids on the buyer's behalf, only as much as needed to
 * keep them in front, and never past the maximum. Maximums are public, which the box says plainly.
 *   listing  the ListingDetail
 *   myMax    this buyer's current maximum on this auction, or null
 *   leading  whether this buyer currently has the highest bid
 */
export function AutoBidBox({ listing, myMax, leading }) {
  const queryClient = useQueryClient()
  const id = String(listing.id)
  const [editing, setEditing] = useState(false)
  const [typed, setTyped] = useState('')
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  // A leader only has to cover their own price; anyone else has to be able to beat the current one.
  const floor = leading ? listing.current_price : listing.min_next_bid

  const refresh = () => {
    for (const key of [['auto-bids', id], ['my-auto-bids'], ['bids', id], ['my-bids'], ['listings']]) {
      queryClient.invalidateQueries({ queryKey: key })
    }
  }

  const save = useMutation({
    mutationFn: (amount) => api(`/listings/${id}/auto-bid`, { method: 'PUT', body: { max_amount: amount } }),
    onSuccess: (result) => {
      queryClient.setQueryData(['listing', id], result.listing) // the app may already have bid for them
      refresh()
      setEditing(false)
      setTyped('')
      setError(null)
      setNotice(`Maximum set to ${formatRupees(result.auto_bid.max_amount)}.`)
    },
    onError: (e) => {
      setNotice(null)
      setError(errorMessage(e))
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
    setError(null)
    save.mutate(amount)
  }

  const showForm = myMax == null || editing

  return (
    <section className="auto-box" aria-label="Automatic bidding">
      <div className="auto-head">
        <strong>Automatic bidding</strong>
        <span className="muted small">
          Set a maximum and the app bids for you, only as much as needed to keep you in front. Maximums are public.
        </span>
      </div>

      {myMax != null && !editing && (
        <p className="auto-current">
          Your maximum: <strong>{formatRupees(myMax)}</strong>
          <span className="auto-actions">
            <button type="button" className="link-button" onClick={() => { setEditing(true); setTyped(String(myMax)); setNotice(null) }}>
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
          <label htmlFor="auto-max" className="sr-only">Your maximum (₹)</label>
          <div className="bid-row">
            <input
              id="auto-max"
              inputMode="numeric"
              autoComplete="off"
              placeholder={floor != null ? `At least ${floor}` : 'Maximum in ₹'}
              value={typed}
              onChange={(e) => { setTyped(e.target.value); setError(null) }}
              aria-invalid={error ? 'true' : undefined}
            />
            <button className="btn btn-ghost" disabled={save.isPending}>
              {save.isPending ? 'Saving…' : myMax == null ? 'Set maximum' : 'Update'}
            </button>
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
