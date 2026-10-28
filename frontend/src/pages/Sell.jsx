import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, serverNow } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { PhotoPicker } from '../components/PhotoPicker'
import { CATEGORIES, CONDITIONS } from '../lib/format'
import {
  DURATION_PRESETS,
  MAX_DESCRIPTION,
  MAX_TITLE,
  parseLocalInput,
  toLocalInputValue,
  validateListing,
} from '../lib/listingForm'

const EMPTY = {
  title: '',
  category: '',
  condition: '',
  description: '',
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

export function Sell() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [values, setValues] = useState(EMPTY)
  const [files, setFiles] = useState([])
  const [submitted, setSubmitted] = useState(false)
  const [serverError, setServerError] = useState(null)
  // Set the instant a publish starts. `publish.isPending` only flips after React re-renders, so a fast
  // double-tap could otherwise send the form twice and create two identical auctions.
  const inFlight = useRef(false)

  const set = (name) => (event) => setValues((v) => ({ ...v, [name]: event.target.value }))
  // Re-checked on every render so messages update (and clear) as the user fixes things.
  const errors = submitted ? validateListing(values, files, serverNow()) : {}

  function pickDuration(ms) {
    setValues((v) => ({ ...v, closesAt: toLocalInputValue(new Date(serverNow() + ms)) }))
  }

  const publish = useMutation({
    mutationFn: (formData) => api('/listings', { method: 'POST', form: formData }),
    onSuccess: (listing) => {
      queryClient.invalidateQueries({ queryKey: ['listings'] })
      queryClient.invalidateQueries({ queryKey: ['my-listings'] })
      navigate(`/listings/${listing.id}`, { state: { published: true } })
    },
    onError: (e) => {
      inFlight.current = false // let the seller fix the problem and try again
      setServerError(errorMessage(e))
    },
  })

  function onSubmit(event) {
    event.preventDefault()
    if (inFlight.current) return
    setSubmitted(true)
    setServerError(null)
    if (Object.keys(validateListing(values, files, serverNow())).length > 0) return

    const form = new FormData()
    form.append('title', values.title.trim())
    form.append('category', values.category)
    form.append('condition', values.condition)
    form.append('description', values.description.trim())
    form.append('starting_price', values.startingPrice.trim().replace(/,/g, ''))
    form.append('min_increment', values.minIncrement.trim().replace(/,/g, ''))
    // The picker gives local time with no zone; the server needs an absolute moment, so send UTC.
    form.append('closes_at', parseLocalInput(values.closesAt).toISOString())
    files.forEach((file) => form.append('images', file))
    inFlight.current = true
    publish.mutate(form)
  }

  const verified = user?.is_verified

  return (
    <section>
      <h1>Sell an item</h1>
      <p className="muted">List it as an auction. Students bid, and the highest bid when the timer ends wins.</p>

      {user && !verified && (
        <p className="warn-box" role="status">
          Verify your campus email before you can list items. <Link to="/verify">Enter your code</Link>
        </p>
      )}

      <form onSubmit={onSubmit} className="sell-form card" noValidate>
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
            placeholder="Age, any wear or damage, what's included, where to collect it…"
          />
          <FieldError message={errors.description} />
        </label>

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

        <div className="photos">
          <span className="label-text">Photos</span>
          <PhotoPicker files={files} onChange={setFiles} error={errors.photos} />
        </div>

        {serverError && (
          <p className="error" role="alert">
            {serverError}
          </p>
        )}
        <div className="form-actions">
          <button className="btn btn-primary" disabled={publish.isPending || !verified}>
            {publish.isPending ? 'Publishing…' : 'Publish listing'}
          </button>
          <Link to="/" className="btn btn-ghost">
            Cancel
          </Link>
        </div>
      </form>
    </section>
  )
}
