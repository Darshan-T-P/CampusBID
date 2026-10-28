import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { PasswordField } from '../components/PasswordField'
import { YEARS, formatRupees, yearLabel } from '../lib/format'
import { memberSince, profileChanges, validatePasswordChange, validateProfile } from '../lib/profileForm'
import { DEPARTMENTS, passwordStrength } from '../lib/registerForm'

/** One number with a label. `to` makes the whole tile a link. */
function Stat({ value, label, to, tone }) {
  const body = (
    <>
      <strong className={`stat-value ${tone ? `stat-${tone}` : ''}`}>{value}</strong>
      <span className="stat-label">{label}</span>
    </>
  )
  return to ? (
    <Link to={to} className="stat">{body}</Link>
  ) : (
    <div className="stat">{body}</div>
  )
}

function Summary() {
  const query = useQuery({ queryKey: ['profile-summary'], queryFn: () => api('/me/summary'), refetchInterval: 30_000 })
  if (query.isPending) return <p className="muted">Loading your summary…</p>
  if (query.isError) return <p className="error" role="alert">{errorMessage(query.error)}</p>
  const { selling, buying, unread_notifications: unread } = query.data

  return (
    <div className="summary-grid">
      <section className="card summary-card" aria-labelledby="selling-h">
        <div className="summary-head">
          <h2 id="selling-h"><Icon name="tag" size={18} /> Selling</h2>
          <Link to="/my/listings" className="link-button">My listings</Link>
        </div>
        <div className="stats">
          <Stat value={selling.open} label="Open auctions" to="/my/listings" />
          <Stat value={selling.awaiting_decision} label="Need your decision" to="/my/listings" tone={selling.awaiting_decision ? 'alert' : undefined} />
          <Stat value={selling.awaiting_handover} label="Awaiting handover" to="/my/listings" />
          <Stat value={selling.sold} label="Sold" />
          <Stat value={selling.unsold + selling.other} label="Unsold or cancelled" />
          <Stat value={formatRupees(selling.earned)} label="Earned" tone="good" />
        </div>
        <p className="muted small">{selling.total} {selling.total === 1 ? 'listing' : 'listings'} created in total.</p>
      </section>

      <section className="card summary-card" aria-labelledby="buying-h">
        <div className="summary-head">
          <h2 id="buying-h"><Icon name="gavel" size={18} /> Buying</h2>
          <Link to="/my/bids" className="link-button">My bids</Link>
        </div>
        <div className="stats">
          <Stat value={buying.open} label="Active bids" to="/my/bids" />
          <Stat value={buying.leading} label="You are leading" to="/my/bids" tone={buying.leading ? 'good' : undefined} />
          <Stat value={buying.outbid} label="Outbid" to="/my/bids" tone={buying.outbid ? 'alert' : undefined} />
          <Stat value={buying.won} label="Won" />
          <Stat value={formatRupees(buying.spent)} label="Spent" />
          <Stat value={buying.automatic_maximums} label="Automatic maximums" />
        </div>
        <p className="muted small">
          {buying.bids_placed} {buying.bids_placed === 1 ? 'bid' : 'bids'} placed on {buying.auctions} {buying.auctions === 1 ? 'auction' : 'auctions'}.
          {unread > 0 && <> You have {unread} unread {unread === 1 ? 'notification' : 'notifications'}.</>}
        </p>
      </section>
    </div>
  )
}

function EditProfile({ user }) {
  const { updateProfile } = useAuth()
  const [values, setValues] = useState({
    displayName: user.display_name,
    department: user.department ?? '',
    year: user.year_of_study ? String(user.year_of_study) : '',
  })
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)

  const set = (name) => (e) => { setValues((v) => ({ ...v, [name]: e.target.value })); setNotice(null) }
  const errors = submitted ? validateProfile(values) : {}

  async function onSubmit(event) {
    event.preventDefault()
    setSubmitted(true)
    setError(null)
    if (Object.keys(validateProfile(values)).length > 0) return
    const changes = profileChanges(user, values)
    if (Object.keys(changes).length === 0) return setNotice('Nothing to save: your details are already up to date.')
    setBusy(true)
    try {
      await updateProfile(changes)
      setNotice('Profile updated.')
      setSubmitted(false)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card" aria-labelledby="edit-h">
      <h2 id="edit-h"><Icon name="user" size={18} /> Your details</h2>
      <form onSubmit={onSubmit} className="form" noValidate>
        <div className="form-field">
          <label htmlFor="p-name">Display name</label>
          <input id="p-name" value={values.displayName} onChange={set('displayName')} maxLength={80} aria-invalid={errors.displayName ? 'true' : undefined} />
          <div className="field-notes">
            {errors.displayName ? <small className="field-error" role="alert">{errors.displayName}</small> : <small className="muted">Shown on your bids and listings.</small>}
          </div>
        </div>
        <div className="form-row">
          <div className="form-field">
            <label htmlFor="p-year">Year of study</label>
            <select id="p-year" value={values.year} onChange={set('year')}>
              <option value="">Not set</option>
              {YEARS.map((y) => <option key={y.value} value={y.value}>{y.label}</option>)}
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="p-dept">Department</label>
            <input id="p-dept" list="p-dept-options" value={values.department} onChange={set('department')} maxLength={80} aria-invalid={errors.department ? 'true' : undefined} />
            <datalist id="p-dept-options">{DEPARTMENTS.map((d) => <option key={d} value={d} />)}</datalist>
            <div className="field-notes">{errors.department && <small className="field-error" role="alert">{errors.department}</small>}</div>
          </div>
        </div>
        <div className="form-field">
          <label htmlFor="p-email">Campus email</label>
          <input id="p-email" value={user.email} readOnly disabled />
          <small className="muted">Only you can see this. It can't be changed here.</small>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        {notice && <p className="success-box" role="status">{notice}</p>}
        <div><button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button></div>
      </form>
    </section>
  )
}

function ChangePassword() {
  const { changePassword } = useAuth()
  const [values, setValues] = useState({ current: '', next: '', confirm: '' })
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)

  const set = (name) => (e) => { setValues((v) => ({ ...v, [name]: e.target.value })); setNotice(null) }
  const all = validatePasswordChange(values)
  const errors = submitted ? all : {}
  const strength = passwordStrength(values.next)

  async function onSubmit(event) {
    event.preventDefault()
    setSubmitted(true)
    setError(null)
    if (Object.keys(all).length > 0) return
    setBusy(true)
    try {
      await changePassword(values.current, values.next)
      setValues({ current: '', next: '', confirm: '' })
      setSubmitted(false)
      setNotice('Password changed. Your other devices have been signed out.')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card" aria-labelledby="pw-h">
      <h2 id="pw-h"><Icon name="lock" size={18} /> Change password</h2>
      <form onSubmit={onSubmit} className="form" noValidate>
        <PasswordField id="pw-current" label="Current password" autoComplete="current-password" value={values.current} onChange={set('current')} error={errors.current} />
        <PasswordField id="pw-new" label="New password" autoComplete="new-password" value={values.next} onChange={set('next')} error={errors.next} hint="At least 8 characters.">
          {values.next && !errors.next && (
            <span className={`strength strength-${strength.score}`} aria-live="polite">
              <span className="strength-bar"><span style={{ width: `${(strength.score / 4) * 100}%` }} /></span>
              {strength.label}
            </span>
          )}
        </PasswordField>
        <PasswordField id="pw-confirm" label="Confirm new password" autoComplete="new-password" value={values.confirm} onChange={set('confirm')} error={errors.confirm}>
          {values.confirm && values.confirm === values.next && <small className="match-ok">Passwords match</small>}
        </PasswordField>
        {error && <p className="error" role="alert">{error}</p>}
        {notice && <p className="success-box" role="status">{notice}</p>}
        <div><button className="btn btn-primary" disabled={busy}>{busy ? 'Changing…' : 'Change password'}</button></div>
        <small className="muted">
          Forgotten your password? Email-based reset isn't available yet, so change it here while you're signed in.
        </small>
      </form>
    </section>
  )
}

export function Profile() {
  const { user } = useAuth()
  if (!user) return null // RequireAuth shows the loading state; nothing to render until we know who this is
  const academic = [yearLabel(user.year_of_study), user.department].filter(Boolean).join(' · ')

  return (
    <section className="profile">
      <div className="card profile-head">
        <span className="avatar avatar-xl" aria-hidden="true">{user.display_name.charAt(0).toUpperCase()}</span>
        <div className="profile-id">
          <h1>{user.display_name}</h1>
          <p className="muted">{user.email}</p>
          <p className="profile-meta">
            {user.is_verified ? (
              <span className="verified-student-chip"><Icon name="shield" size={13} /> Verified student</span>
            ) : (
              <Link to="/verify" className="warn-chip">Email not verified</Link>
            )}
            {academic && <span className="muted">{academic}</span>}
            <span className="muted">Member since {memberSince(user.created_at)}</span>
          </p>
        </div>
      </div>

      <h2 className="section-title">Summary</h2>
      <Summary />

      <h2 className="section-title">Account</h2>
      <div className="account-grid">
        {/* No `key` on the user's values: re-creating the form after a save would erase its "Profile updated" message. */}
        <EditProfile user={user} />
        <ChangePassword />
      </div>
    </section>
  )
}
