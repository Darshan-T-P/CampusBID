import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, serverNow } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { PhotoPicker } from '../components/PhotoPicker'
import { PriceSuggestion } from '../components/PriceSuggestion'
import { CATEGORIES, CONDITIONS, categoryLabel, conditionLabel, formatRemaining, formatRupees } from '../lib/format'
import { parseAmount } from '../lib/bidding'
import {
  COMMON_HANDOVER_SPOTS,
  DURATION_PRESETS,
  MAX_DESCRIPTION,
  MAX_HANDOVER_SPOT,
  MAX_TITLE,
  parseLocalInput,
  toLocalInputValue,
  validateListing,
} from '../lib/listingForm'
import { usePageTitle } from '../hooks/usePageTitle'

const EMPTY = {
  title: '',
  category: '',
  condition: '',
  description: '',
  handoverSpot: '',
  startingPrice: '',
  minIncrement: '10',
  closesAt: '',
}

/** A message under a field, shown once the user has tried to submit. */
function FieldError({ id, message }) {
  if (!message) return null
  return (
    <small id={id} className="field-error" role="alert">
      {message}
    </small>
  )
}

/** How the listing will look in the browse grid, updating as the seller types. Not clickable. */
function ListingPreview({ values, files, sellerName }) {
  const cover = useMemo(() => (files[0] ? URL.createObjectURL(files[0]) : null), [files])
  useEffect(() => () => cover && URL.revokeObjectURL(cover), [cover])

  const price = parseAmount(values.startingPrice)
  const closes = parseLocalInput(values.closesAt)
  const remaining = closes ? closes.getTime() - serverNow() : null

  return (
    <div className="listing-card listing-preview" aria-label="Preview of your listing">
      <div className="thumb">
        {cover ? (
          <img src={cover} alt="" />
        ) : (
          <div className="thumb-empty">
            <Icon name="package" size={26} />
            <span>Your first photo appears here</span>
          </div>
        )}
        <span className="thumb-category">{values.category ? categoryLabel(values.category) : 'Category'}</span>
      </div>
      <div className="listing-body">
        <h3 className="listing-title">{values.title.trim() || 'Your item title'}</h3>
        <div className="chips">
          <span className="chip">{values.condition ? conditionLabel(values.condition) : 'Condition'}</span>
          <span className="seller-by">by {sellerName}</span>
        </div>
        <div className="price-row">
          <div>
            <span className="price-label">Starting price</span>
            <strong className="price">{price ? formatRupees(price) : '₹ -'}</strong>
          </div>
          <span className="bid-count-pill">0 bids</span>
        </div>
        <div className="listing-meta">
          <span className="countdown countdown-calm">{remaining && remaining > 0 ? `${formatRemaining(remaining)} left` : 'Set a closing time'}</span>
          {values.handoverSpot.trim() && (
            <span className="card-handover-spot">
              <Icon name="pin" size={13} /> {values.handoverSpot.trim()}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

const TIPS = [
  'Use clear, well-lit photos from a few angles. The first photo is the cover.',
  'Describe any wear or damage and what is included. Honest listings get more bids.',
  'End the auction when students are around, and give it at least a day.',
  'A low starting price attracts early bids; the minimum raise keeps the bidding moving.',
  'A bid in the last 30 seconds extends the auction by a minute, so you can never be sniped.',
  'Meet at a public spot on campus, in daylight.',
]

export function Sell() {
  usePageTitle('Sell an item')
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [values, setValues] = useState(EMPTY)
  const [files, setFiles] = useState([])
  const [submitted, setSubmitted] = useState(false)
  const [serverError, setServerError] = useState(null)
  // The server found a similar live listing of this seller's and is asking "is this a second item?".
  const [duplicate, setDuplicate] = useState(null)
  const duplicateBox = useRef(null)
  const lastForm = useRef(null) // what was just sent, so "Yes, it's a second one" can send it again with the confirmation
  // Set the instant a publish starts. `publish.isPending` only flips after React re-renders, so a fast
  // double-tap could otherwise send the form twice and create two identical auctions.
  const inFlight = useRef(false)

  const set = (name) => (event) => setValues((v) => ({ ...v, [name]: event.target.value }))
  // Re-checked on every render so messages update (and clear) as the user fixes things.
  const errors = submitted ? validateListing(values, files, serverNow()) : {}

  function pickDuration(ms) {
    setValues((v) => ({ ...v, closesAt: toLocalInputValue(new Date(serverNow() + ms)) }))
  }

  useEffect(() => {
    // The prompt sits below the form while the Publish bar stays in view, so bring it to the seller's attention.
    if (duplicate) duplicateBox.current?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  }, [duplicate])

  const publish = useMutation({
    mutationFn: (formData) => api('/listings', { method: 'POST', form: formData }),
    onSuccess: (listing) => {
      queryClient.invalidateQueries({ queryKey: ['listings'] })
      queryClient.invalidateQueries({ queryKey: ['my-listings'] })
      navigate(`/listings/${listing.id}`, { state: { published: true } })
    },
    onError: (e) => {
      inFlight.current = false // let the seller fix the problem and try again
      if (e.code === 'possible_duplicate') {
        setDuplicate({ message: e.message, existing: e.detail?.existing, reason: e.detail?.reason })
        return
      }
      setServerError(errorMessage(e))
    },
  })

  function onSubmit(event) {
    event.preventDefault()
    if (inFlight.current) return
    setSubmitted(true)
    setServerError(null)
    setDuplicate(null)
    if (Object.keys(validateListing(values, files, serverNow())).length > 0) return

    const form = new FormData()
    form.append('title', values.title.trim())
    form.append('category', values.category)
    form.append('condition', values.condition)
    form.append('description', values.description.trim())
    if (values.handoverSpot.trim()) form.append('handover_spot', values.handoverSpot.trim())
    form.append('starting_price', values.startingPrice.trim().replace(/,/g, ''))
    form.append('min_increment', values.minIncrement.trim().replace(/,/g, ''))
    // The picker gives local time with no zone; the server needs an absolute moment, so send UTC.
    form.append('closes_at', parseLocalInput(values.closesAt).toISOString())
    files.forEach((file) => form.append('images', file))
    lastForm.current = form
    inFlight.current = true
    publish.mutate(form)
  }

  // "Yes, this is a second item": send exactly the same form again, with the seller's confirmation.
  function postAnyway() {
    if (inFlight.current || !lastForm.current) return
    lastForm.current.set('confirm_duplicate', 'true')
    setDuplicate(null)
    setServerError(null)
    inFlight.current = true
    publish.mutate(lastForm.current)
  }

  const verified = user?.is_verified

  return (
    <section className="sell-page">
      <h1>Sell an item</h1>
      <p className="muted">List it as an auction. Students bid, and the highest bid when the timer ends wins.</p>

      {user && !verified && (
        <p className="warn-box" role="status">
          Verify your campus email before you can list items. <Link to="/verify">Enter your code</Link>
        </p>
      )}

      <div className="sell-layout">
        <form onSubmit={onSubmit} className="sell-main" noValidate>
          <section className="card form-section" aria-labelledby="s-details">
            <div>
              <h2 id="s-details">Item details</h2>
              <p className="muted small">What buyers see first.</p>
            </div>
            <label>
              Title
              <input
                value={values.title}
                onChange={set('title')}
                maxLength={MAX_TITLE}
                placeholder="e.g. Hero Sprint 21-speed cycle"
                aria-invalid={errors.title ? 'true' : undefined}
                aria-describedby="err-title"
              />
              <FieldError id="err-title" message={errors.title} />
            </label>
            <div className="form-row">
              <label>
                Category
                <select value={values.category} onChange={set('category')} aria-invalid={errors.category ? 'true' : undefined}>
                  <option value="">Choose…</option>
                  {CATEGORIES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <FieldError message={errors.category} />
              </label>
              <label>
                Condition
                <select value={values.condition} onChange={set('condition')} aria-invalid={errors.condition ? 'true' : undefined}>
                  <option value="">Choose…</option>
                  {CONDITIONS.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <FieldError message={errors.condition} />
              </label>
            </div>
            <label>
              <span>
                Description <span className="muted">(optional)</span>
              </span>
              <textarea
                rows={5}
                value={values.description}
                onChange={set('description')}
                maxLength={MAX_DESCRIPTION}
                placeholder="Age, any wear or damage, what's included, additional details…"
              />
              <FieldError message={errors.description} />
            </label>
          </section>

          <section className="card form-section" aria-labelledby="s-photos">
            <div>
              <h2 id="s-photos">Photos</h2>
              <p className="muted small">Add up to 5. The first one is the cover.</p>
            </div>
            <PhotoPicker files={files} onChange={setFiles} error={errors.photos} />
          </section>

          <section className="card form-section" aria-labelledby="s-price">
            <div>
              <h2 id="s-price">Price and timing</h2>
              <p className="muted small">Bidding starts at your price and rises by at least the minimum raise.</p>
            </div>
            <PriceSuggestion
              category={values.category}
              condition={values.condition}
              title={values.title}
              onUse={(amount) => setValues((v) => ({ ...v, startingPrice: String(amount) }))}
            />
            <div className="form-row">
              <label>
                Starting price (₹)
                <input
                  inputMode="numeric"
                  value={values.startingPrice}
                  onChange={set('startingPrice')}
                  aria-invalid={errors.startingPrice ? 'true' : undefined}
                  aria-describedby="err-start"
                />
                <small className="muted">The lowest first bid you'll accept.</small>
                <FieldError id="err-start" message={errors.startingPrice} />
              </label>
              <label>
                Minimum raise (₹)
                <input
                  inputMode="numeric"
                  value={values.minIncrement}
                  onChange={set('minIncrement')}
                  aria-invalid={errors.minIncrement ? 'true' : undefined}
                  aria-describedby="err-inc"
                />
                <small className="muted">Each bid must beat the last by at least this much.</small>
                <FieldError id="err-inc" message={errors.minIncrement} />
              </label>
            </div>
            <fieldset className="closing">
              <legend>Auction ends</legend>
              <div className="presets">
                {DURATION_PRESETS.map((p) => (
                  <button key={p.label} type="button" className="btn btn-ghost btn-sm" onClick={() => pickDuration(p.ms)}>
                    In {p.label}
                  </button>
                ))}
              </div>
              <input
                type="datetime-local"
                value={values.closesAt}
                onChange={set('closesAt')}
                aria-label="Closing date and time"
                aria-invalid={errors.closesAt ? 'true' : undefined}
                aria-describedby="err-close"
              />
              <small className="muted">Between 10 minutes and 30 days from now, in your local time.</small>
              <FieldError id="err-close" message={errors.closesAt} />
            </fieldset>
          </section>

          <section className="card form-section" aria-labelledby="s-handover">
            <div>
              <h2 id="s-handover">Handover</h2>
              <p className="muted small">Where on campus you'll meet the winner. Optional.</p>
            </div>
            <label>
              Campus handover spot
              <input
                value={values.handoverSpot}
                onChange={set('handoverSpot')}
                maxLength={MAX_HANDOVER_SPOT}
                placeholder="e.g. Central Library Gate, Main Canteen, Hostel A…"
                aria-invalid={errors.handoverSpot ? 'true' : undefined}
                aria-describedby="err-handover"
              />
              <div className="presets">
                {COMMON_HANDOVER_SPOTS.map((spot) => (
                  <button
                    key={spot}
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setValues((v) => ({ ...v, handoverSpot: spot }))}
                  >
                    <Icon name="pin" size={13} /> {spot}
                  </button>
                ))}
              </div>
              <small className="muted">A public spot in daylight is best for inspecting the item and handing it over.</small>
              <FieldError id="err-handover" message={errors.handoverSpot} />
            </label>
          </section>

          {duplicate && (
            <div className="duplicate-box" role="alertdialog" aria-labelledby="dup-h" ref={duplicateBox}>
              <h3 id="dup-h">
                <Icon name="package" size={17} /> Is this a second item?
              </h3>
              <p>{duplicate.message}</p>
              {duplicate.existing && (
                <p className="muted small">
                  <Link to={`/listings/${duplicate.existing.id}`}>{duplicate.existing.title}</Link> · {formatRupees(duplicate.existing.price)}
                </p>
              )}
              <div className="form-actions">
                <button type="button" className="btn btn-primary btn-sm" onClick={postAnyway} disabled={publish.isPending}>
                  Yes, it's a second item: post it
                </button>
                {duplicate.existing && (
                  <Link to={`/listings/${duplicate.existing.id}`} className="btn btn-ghost btn-sm">
                    No, show my existing listing
                  </Link>
                )}
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDuplicate(null)}>
                  Change this one
                </button>
              </div>
            </div>
          )}
          {serverError && (
            <p className="error" role="alert">
              {serverError}
            </p>
          )}
          <div className="sell-actions">
            <Link to="/" className="btn btn-ghost">
              Cancel
            </Link>
            <button className="btn btn-primary" disabled={publish.isPending || !verified}>
              { 'Publish listing'}
            </button>
          </div>
        </form>

        <aside className="sell-aside" aria-label="Preview and tips">
          <div>
            <h2 className="aside-title">Preview</h2>
            <ListingPreview values={values} files={files} sellerName={user?.display_name ?? 'you'} />
          </div>
          <div className="card tips">
            <h2 className="aside-title">Tips for a good listing</h2>
            <ul>
              {TIPS.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </section>
  )
}
