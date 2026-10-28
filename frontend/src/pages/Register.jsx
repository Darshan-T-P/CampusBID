import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { PasswordField } from '../components/PasswordField'
import { YEARS } from '../lib/format'
import { DEPARTMENTS, REQUIRED_EMAIL_SUFFIX, passwordStrength, validateRegistration } from '../lib/registerForm'

const EMPTY = { email: '', displayName: '', year: '', department: '', password: '', confirm: '' }

export function Register() {
  const { register, isSignedIn, user, loading } = useAuth()
  const navigate = useNavigate()

  const [values, setValues] = useState(EMPTY)
  const [touched, setTouched] = useState({}) // fields the person has left at least once
  const [submitted, setSubmitted] = useState(false)
  const [serverError, setServerError] = useState(null)
  const [busy, setBusy] = useState(false)

  // Signing in flips isSignedIn before onSubmit navigates, so wait for the profile and route by verification.
  if (isSignedIn) return loading ? null : <Navigate to={user && !user.is_verified ? '/verify' : '/'} replace />

  const set = (name) => (event) => setValues((v) => ({ ...v, [name]: event.target.value }))
  const blur = (name) => () => setTouched((t) => ({ ...t, [name]: true }))
  // Show a message once the person has left the field or tried to submit, never while they're still typing.
  const all = validateRegistration(values)
  const errors = Object.fromEntries(Object.entries(all).filter(([name]) => submitted || touched[name]))
  const strength = passwordStrength(values.password)
  const matches = values.confirm !== '' && values.confirm === values.password

  async function onSubmit(event) {
    event.preventDefault()
    setSubmitted(true)
    setServerError(null)
    if (Object.keys(all).length > 0) return
    setBusy(true)
    try {
      const result = await register(values.email.trim(), values.displayName.trim(), values.password, {
        department: values.department.trim(),
        year_of_study: Number(values.year),
      })
      navigate(result.is_verified ? '/' : '/verify', { replace: true })
    } catch (e) {
      setServerError(errorMessage(e))
      setBusy(false)
    }
  }

  return (
    <div className="card auth-card">
      <h1>Create your account</h1>
      <p className="muted">Only campus email addresses can register. Your email is never shown to other students.</p>

      <form onSubmit={onSubmit} className="form" noValidate>
        <div className="form-field">
          <label htmlFor="reg-email">Campus email</label>
          <input
            id="reg-email"
            type="email"
            autoComplete="email"
            placeholder={`you@college${REQUIRED_EMAIL_SUFFIX}`}
            value={values.email}
            onChange={set('email')}
            onBlur={blur('email')}
            aria-invalid={errors.email ? 'true' : undefined}
            aria-describedby="reg-email-note"
          />
          <div id="reg-email-note" className="field-notes">
            {errors.email ? <small className="field-error" role="alert">{errors.email}</small> : <small className="muted">Must end in {REQUIRED_EMAIL_SUFFIX}</small>}
          </div>
        </div>

        <div className="form-field">
          <label htmlFor="reg-name">Display name</label>
          <input
            id="reg-name"
            autoComplete="nickname"
            maxLength={80}
            value={values.displayName}
            onChange={set('displayName')}
            onBlur={blur('displayName')}
            aria-invalid={errors.displayName ? 'true' : undefined}
            aria-describedby="reg-name-note"
          />
          <div id="reg-name-note" className="field-notes">
            {errors.displayName ? <small className="field-error" role="alert">{errors.displayName}</small> : <small className="muted">The name other students see on your bids and listings.</small>}
          </div>
        </div>

        <div className="form-row">
          <div className="form-field">
            <label htmlFor="reg-year">Year of study</label>
            <select id="reg-year" value={values.year} onChange={set('year')} onBlur={blur('year')} aria-invalid={errors.year ? 'true' : undefined}>
              <option value="">Select year</option>
              {YEARS.map((y) => (
                <option key={y.value} value={y.value}>{y.label}</option>
              ))}
            </select>
            <div className="field-notes">{errors.year && <small className="field-error" role="alert">{errors.year}</small>}</div>
          </div>
          <div className="form-field">
            <label htmlFor="reg-dept">Department</label>
            <input
              id="reg-dept"
              list="dept-options"
              maxLength={80}
              placeholder="e.g. Computer Science"
              value={values.department}
              onChange={set('department')}
              onBlur={blur('department')}
              aria-invalid={errors.department ? 'true' : undefined}
            />
            <datalist id="dept-options">
              {DEPARTMENTS.map((d) => (
                <option key={d} value={d} />
              ))}
            </datalist>
            <div className="field-notes">{errors.department && <small className="field-error" role="alert">{errors.department}</small>}</div>
          </div>
        </div>
        <small className="muted form-aside">Your year and department are shown next to your name on items you sell.</small>

        <PasswordField
          id="reg-password"
          label="Password"
          autoComplete="new-password"
          value={values.password}
          onChange={set('password')}
          onBlur={blur('password')}
          error={errors.password}
          hint="At least 8 characters."
        >
          {values.password && !errors.password && (
            <span className={`strength strength-${strength.score}`} aria-live="polite">
              <span className="strength-bar"><span style={{ width: `${(strength.score / 4) * 100}%` }} /></span>
              {strength.label}
            </span>
          )}
        </PasswordField>

        <PasswordField
          id="reg-confirm"
          label="Confirm password"
          autoComplete="new-password"
          value={values.confirm}
          onChange={set('confirm')}
          onBlur={blur('confirm')}
          error={errors.confirm}
        >
          {matches && <small className="match-ok">Passwords match</small>}
        </PasswordField>

        {serverError && (
          <p className="error" role="alert">
            {serverError}
          </p>
        )}
        <button className="btn btn-primary btn-block" disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <p className="muted">
        Already registered? <Link to="/login">Sign in</Link>
      </p>
    </div>
  )
}
