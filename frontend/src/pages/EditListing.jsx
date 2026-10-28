import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, api, mediaUrl, serverNow } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { CATEGORIES, CONDITIONS } from '../lib/format'
import {
  FROZEN_AFTER_BID,
  MAX_DESCRIPTION,
  MAX_HANDOVER_SPOT,
  MAX_PHOTOS,
  MAX_TITLE,
  PHOTO_TYPES,
  changedFields,
  toPatch,
  validateEdit,
  validatePhotos,
  valuesFromListing,
} from '../lib/listingForm'

function FieldError({ message }) {
  return message ? <small className="field-error" role="alert">{message}</small> : null
}

/** Photos are changed straight away (each add/remove is its own request), separate from the text fields. */
function PhotoEditor({ listing }) {
  const queryClient = useQueryClient()
  const input = useRef(null)
  const [error, setError] = useState(null)
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['listing', String(listing.id)] })
    queryClient.invalidateQueries({ queryKey: ['listings'] })
  }

  const remove = useMutation({
    mutationFn: (imageId) => api(`/listings/${listing.id}/images/${imageId}`, { method: 'DELETE' }),
    onSuccess: () => { setError(null); refresh() },
    onError: (e) => setError(errorMessage(e)),
  })
  const add = useMutation({
    mutationFn: (files) => {
      const form = new FormData()
      files.forEach((f) => form.append('images', f))
      return api(`/listings/${listing.id}/images`, { method: 'POST', form })
    },
    onSuccess: () => { setError(null); refresh() },
    onError: (e) => setError(errorMessage(e)),
  })

  function onPick(event) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (files.length === 0) return
    const problem = validatePhotos(files) || (listing.images.length + files.length > MAX_PHOTOS ? `A listing can have at most ${MAX_PHOTOS} photos` : null)
    if (problem) return setError(problem)
    add.mutate(files)
  }

  const busy = add.isPending || remove.isPending
  return (
    <div className="photo-picker">
      <div className="photo-grid">
        {listing.images.map((src, i) => (
          <figure key={listing.image_ids[i]} className="photo-tile">
            <img src={mediaUrl(src)} alt={`Photo ${i + 1}`} />
            {i === 0 && <figcaption className="photo-cover">Cover</figcaption>}
            {listing.images.length > 1 && (
              <button type="button" className="photo-remove" disabled={busy} aria-label={`Remove photo ${i + 1}`} onClick={() => remove.mutate(listing.image_ids[i])}>
                ×
              </button>
            )}
          </figure>
        ))}
        {listing.images.length < MAX_PHOTOS && (
          <button type="button" className="photo-add" disabled={busy} onClick={() => input.current.click()}>
            {add.isPending ? 'Uploading…' : '+ Add photo'}
          </button>
        )}
      </div>
      <input ref={input} type="file" accept={PHOTO_TYPES.join(',')} multiple hidden onChange={onPick} aria-label="Add photos" />
      <small className="muted">Photo changes are saved straight away. A listing keeps at least one photo.</small>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  )
}

function EditForm({ listing }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [initial] = useState(() => valuesFromListing(listing)) // how it was when this page opened
  const [values, setValues] = useState(initial)
  const [submitted, setSubmitted] = useState(false)
  const [serverError, setServerError] = useState(null)
  const inFlight = useRef(false)

  const locked = listing.bid_count > 0
  const isLocked = (key) => locked && FROZEN_AFTER_BID.includes(key)
  const set = (name) => (event) => setValues((v) => ({ ...v, [name]: event.target.value }))

  const changed = changedFields(initial, values)
  const errors = submitted ? validateEdit(values, changed, serverNow()) : {}

  const save = useMutation({
    mutationFn: (body) => api(`/listings/${listing.id}`, { method: 'PATCH', body }),
    onSuccess: () => {
      for (const key of [['listing', String(listing.id)], ['listings'], ['my-listings']]) queryClient.invalidateQueries({ queryKey: key })
      navigate(`/listings/${listing.id}`, { state: { saved: true } })
    },
    onError: (e) => {
      inFlight.current = false
      setServerError(errorMessage(e))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => api(`/listings/${listing.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-listings'] })
      queryClient.invalidateQueries({ queryKey: ['listings'] })
      navigate('/my-listings')
    },
    onError: (e) => setServerError(errorMessage(e)),
  })

  const cancelMutation = useMutation({
    mutationFn: () => api(`/listings/${listing.id}/cancel`, { method: 'POST' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-listings'] })
      queryClient.invalidateQueries({ queryKey: ['listing', String(listing.id)] })
      queryClient.invalidateQueries({ queryKey: ['listings'] })
      navigate(`/listings/${listing.id}`)
    },
    onError: (e) => setServerError(errorMessage(e)),
  })

  function handleDelete() {
    if (window.confirm('Are you sure you want to permanently delete this listing? This action cannot be undone.')) {
      deleteMutation.mutate()
    }
  }

  function handleCancel() {
    if (window.confirm('Are you sure you want to cancel this auction? Active bidders will be notified that the listing was withdrawn.')) {
      cancelMutation.mutate()
    }
  }

  function onSubmit(event) {
    event.preventDefault()
    if (inFlight.current) return
    setSubmitted(true)
    setServerError(null)
    if (changed.length === 0) return setServerError('You haven\'t changed anything yet.')
    if (Object.keys(validateEdit(values, changed, serverNow())).length > 0) return
    inFlight.current = true
    save.mutate(toPatch(values, changed))
  }

  return (
    <section className="narrow-page">
      <p className="crumbs"><Link to={`/listings/${listing.id}`}>← Back to the auction</Link></p>
      <h1>Edit listing</h1>
      {locked && (
        <p className="warn-box" role="status">
          Bidding has started, so only the description and photos can change. This keeps bidders from being misled about what they're bidding on.
        </p>
      )}

      <form onSubmit={onSubmit} className="sell-form card" noValidate>
        <label>
          Title
          <input value={values.title} onChange={set('title')} maxLength={MAX_TITLE} disabled={isLocked('title')} aria-invalid={errors.title ? 'true' : undefined} />
          <FieldError message={errors.title} />
        </label>
        <div className="form-row">
          <label>
            Category
            <select value={values.category} onChange={set('category')} disabled={isLocked('category')}>
              {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </label>
          <label>
            Condition
            <select value={values.condition} onChange={set('condition')} disabled={isLocked('condition')}>
              {CONDITIONS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </label>
        </div>
        <label>
          <span>Description <span className="muted">(optional)</span></span>
          <textarea rows={5} value={values.description} onChange={set('description')} maxLength={MAX_DESCRIPTION} />
          <FieldError message={errors.description} />
        </label>
        <label>
          <span>Campus Handover Spot <span className="muted">(where to meet on campus)</span></span>
          <input
            value={values.handoverSpot}
            onChange={set('handoverSpot')}
            maxLength={MAX_HANDOVER_SPOT}
            placeholder="e.g. Central Library Gate, Main Canteen…"
          />
          <FieldError message={errors.handoverSpot} />
        </label>
        <div className="form-row">
          <label>
            Starting price (₹)
            <input inputMode="numeric" value={values.startingPrice} onChange={set('startingPrice')} disabled={isLocked('startingPrice')} aria-invalid={errors.startingPrice ? 'true' : undefined} />
            <FieldError message={errors.startingPrice} />
          </label>
          <label>
            Minimum raise (₹)
            <input inputMode="numeric" value={values.minIncrement} onChange={set('minIncrement')} disabled={isLocked('minIncrement')} aria-invalid={errors.minIncrement ? 'true' : undefined} />
            <FieldError message={errors.minIncrement} />
          </label>
        </div>
        <label>
          Auction ends
          <input type="datetime-local" value={values.closesAt} onChange={set('closesAt')} disabled={isLocked('closesAt')} aria-invalid={errors.closesAt ? 'true' : undefined} />
          <small className="muted">Between 10 minutes and 30 days from now, in your local time.</small>
          <FieldError message={errors.closesAt} />
        </label>

        <div className="photos">
          <span className="label-text">Photos</span>
          <PhotoEditor listing={listing} />
        </div>

        {serverError && <p className="error" role="alert">{serverError}</p>}
        <div className="form-actions">
          <button className="btn btn-primary" disabled={save.isPending}>{save.isPending ? 'Saving…' : 'Save changes'}</button>
          <Link to={`/listings/${listing.id}`} className="btn btn-ghost">Cancel</Link>
        </div>
      </form>

      {/* Danger Zone: Withdraw / Delete Listing */}
      <div className="card danger-zone" style={{ marginTop: '24px' }}>
        <h3 style={{ margin: '0 0 8px', color: 'var(--text)' }}>Withdraw or Delete Listing</h3>
        {listing.bid_count === 0 ? (
          <div>
            <p className="muted small" style={{ marginBottom: '12px' }}>
              No bids have been placed on this item yet. You can delete it permanently.
            </p>
            <button
              type="button"
              className="btn btn-danger-text"
              disabled={deleteMutation.isPending}
              onClick={handleDelete}
            >
              {deleteMutation.isPending ? 'Deleting…' : 'Delete listing permanently'}
            </button>
          </div>
        ) : (
          <div>
            <p className="muted small" style={{ marginBottom: '12px' }}>
              This auction has {listing.bid_count} {listing.bid_count === 1 ? 'bid' : 'bids'}. You cannot erase other students' bid history, but you can cancel the auction now. Active bidders will be notified.
            </p>
            <button
              type="button"
              className="btn btn-danger-text"
              disabled={cancelMutation.isPending}
              onClick={handleCancel}
            >
              {cancelMutation.isPending ? 'Cancelling…' : 'Cancel this auction'}
            </button>
          </div>
        )}
      </div>
    </section>
  )
}

export function EditListing() {
  const { id } = useParams()
  const { user } = useAuth()
  const query = useQuery({ queryKey: ['listing', id], queryFn: () => api(`/listings/${id}`) })

  if (query.isPending) return <p className="muted center">Loading…</p>
  if (query.isError) {
    const gone = query.error instanceof ApiError && query.error.status === 404
    return <section className="center"><h1>{gone ? "This auction doesn't exist" : "Couldn't load this auction"}</h1><Link to="/">← Back to browsing</Link></section>
  }
  const listing = query.data
  if (user && listing.seller.id !== user.id) {
    return <section className="center"><h1>Only the seller can edit this</h1><Link to={`/listings/${id}`}>← Back to the auction</Link></section>
  }
  if (listing.status !== 'active') {
    return <section className="center"><h1>This listing can no longer be edited</h1><p className="muted">Only open auctions can be changed.</p><Link to={`/listings/${id}`}>← Back to the auction</Link></section>
  }
  // `key` rebuilds the form if the listing is ever swapped, so it can't show another listing's values.
  return <EditForm key={listing.id} listing={listing} />
}
