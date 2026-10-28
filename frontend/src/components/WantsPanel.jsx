import { useState } from 'react'
import { errorMessage } from '../api/errors'
import { useWants } from '../hooks/useWants'
import { CATEGORIES } from '../lib/format'
import { describeWant, validateWant } from '../lib/wants'
import { Icon } from './Icon'

/** "Never miss what you need": save a search, and get a notification when a matching listing is posted. */
export function WantsPanel() {
  const { query, wants, add, remove } = useWants()
  const [form, setForm] = useState({ keywords: '', category: '', maxPrice: '' })
  const [submitted, setSubmitted] = useState(false)
  const errors = submitted ? validateWant(form) : {}
  const set = (name) => (e) => {
    setForm((f) => ({ ...f, [name]: e.target.value }))
    add.reset()
  }

  async function onSubmit(event) {
    event.preventDefault()
    setSubmitted(true)
    if (Object.keys(validateWant(form)).length > 0) return
    try {
      await add.mutateAsync({ keywords: form.keywords.trim(), category: form.category || null, max_price: form.maxPrice.trim() === '' ? null : Number(form.maxPrice) })
      setForm({ keywords: '', category: '', maxPrice: '' })
      setSubmitted(false)
    } catch {
      /* the error shows below from the mutation state */
    }
  }

  return (
    <section className="card wants-panel" aria-labelledby="wants-h">
      <h2 id="wants-h">
        <Icon name="zap" size={18} /> Alerts for new listings
      </h2>
      <p className="muted small">Tell us what you're looking for. When someone lists a match you'll get a notification, even if you were offline.</p>
      <form onSubmit={onSubmit} className="wants-form" noValidate>
        <div className="form-field">
          <label htmlFor="want-keywords">Words</label>
          <input id="want-keywords" value={form.keywords} onChange={set('keywords')} maxLength={80} placeholder="e.g. cycle" aria-invalid={errors.keywords ? 'true' : undefined} />
        </div>
        <div className="form-field">
          <label htmlFor="want-category">Category</label>
          <select id="want-category" value={form.category} onChange={set('category')}>
            <option value="">Any</option>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="want-price">Up to (₹)</label>
          <input id="want-price" inputMode="numeric" value={form.maxPrice} onChange={set('maxPrice')} placeholder="2000" aria-invalid={errors.maxPrice ? 'true' : undefined} />
        </div>
        <button className="btn btn-primary" disabled={add.isPending}>
          {add.isPending ? 'Saving…' : 'Save alert'}
        </button>
      </form>
      {(errors.form || errors.keywords || errors.maxPrice) && (
        <p className="error" role="alert">
          {errors.form || errors.keywords || errors.maxPrice}
        </p>
      )}
      {add.isError && (
        <p className="error" role="alert">
          {errorMessage(add.error)}
        </p>
      )}
      {query.isSuccess && wants.length === 0 && <p className="muted small">No alerts yet.</p>}
      {wants.length > 0 && (
        <ul className="wants-list">
          {wants.map((w) => (
            <li key={w.id}>
              <span>{describeWant(w)}</span>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => remove.mutate(w.id)} disabled={remove.isPending} aria-label={`Remove alert ${describeWant(w)}`}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
