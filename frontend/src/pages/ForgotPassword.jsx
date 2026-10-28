import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { PasswordField } from '../components/PasswordField'
import { passwordStrength } from '../lib/registerForm'
import { validateForgot, validateReset } from '../lib/resetForm'
import { usePageTitle } from '../hooks/usePageTitle'

/** Two steps on one page: ask for a code by email, then use it to choose a new password. */
export function ForgotPassword() {
  usePageTitle('Reset your password')
  const { isSignedIn, signInWithToken } = useAuth()
  const navigate = useNavigate()

  const [step, setStep] = useState('email')
  const [email, setEmail] = useState('')
  const [values, setValues] = useState({ code: '', password: '', confirm: '' })
  const [touched, setTouched] = useState({})
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(false)

  if (isSignedIn) return <Navigate to="/" replace />

  const emailErrors = validateForgot(email)
  const errors = validateReset(values)
  const strength = passwordStrength(values.password)
  const shown = (field) => (touched[field] ? errors[field] : undefined)
  const set = (field) => (e) => setValues((v) => ({ ...v, [field]: field === 'code' ? e.target.value.replace(/\D/g, '') : e.target.value }))
  const blur = (field) => () => setTouched((t) => ({ ...t, [field]: true }))

  async function requestCode(event) {
    event?.preventDefault()
    setError(null)
    setInfo(null)
    if (emailErrors.email) return setError(emailErrors.email)
    setBusy(true)
    try {
      await api('/auth/forgot-password', { method: 'POST', body: { email } })
      setStep('reset')
      setInfo('If that address has an account, a code is on its way. It expires in 15 minutes.')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function submitReset(event) {
    event.preventDefault()
    setError(null)
    setTouched({ code: true, password: true, confirm: true })
    if (Object.keys(errors).length) return
    setBusy(true)
    try {
      const result = await api('/auth/reset-password', {
        method: 'POST',
        body: { email, code: values.code, new_password: values.password },
      })
      signInWithToken(result.access_token)
      navigate('/', { replace: true })
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  if (step === 'email') {
    return (
      <div className="card auth-card">
        <h1>Reset your password</h1>
        <p className="muted">Enter your campus email and we'll send you a 6-digit code.</p>
        <form onSubmit={requestCode} className="form" noValidate>
          <div className="form-field">
            <label htmlFor="forgot-email">Campus email</label>
            <input id="forgot-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="btn btn-primary" disabled={busy}>
            {busy ? 'Sending…' : 'Send code'}
          </button>
        </form>
        <p className="muted">
          <Link to="/login">Back to sign in</Link>
        </p>
      </div>
    )
  }

  return (
    <div className="card auth-card">
      <h1>Choose a new password</h1>
      <p className="muted">
        Enter the code sent to <strong>{email.trim()}</strong> and pick a new password.
      </p>
      <form onSubmit={submitReset} className="form" noValidate>
        <div className="form-field">
          <label htmlFor="reset-code">Code</label>
          <input
            id="reset-code"
            className="code-input"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={values.code}
            onChange={set('code')}
            onBlur={blur('code')}
            aria-invalid={shown('code') ? 'true' : undefined}
          />
          {shown('code') && <small className="field-error" role="alert">{shown('code')}</small>}
        </div>
        <PasswordField
          id="reset-password"
          label="New password"
          autoComplete="new-password"
          value={values.password}
          onChange={set('password')}
          onBlur={blur('password')}
          error={shown('password')}
          hint="At least 8 characters."
        >
          {values.password && (
            <span className={`strength strength-${strength.score}`} aria-live="polite">
              <span className="strength-bar"><span style={{ width: `${(strength.score / 4) * 100}%` }} /></span>
              {strength.label}
            </span>
          )}
        </PasswordField>
        <PasswordField
          id="reset-confirm"
          label="Confirm new password"
          autoComplete="new-password"
          value={values.confirm}
          onChange={set('confirm')}
          onBlur={blur('confirm')}
          error={shown('confirm')}
        />
        {info && !error && <p className="success">{info}</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="btn btn-primary" disabled={busy}>
          {busy ? 'Saving…' : 'Set new password'}
        </button>
      </form>
      <p className="muted">
        Didn't get it?{' '}
        <button type="button" className="link-button" onClick={requestCode} disabled={busy}>
          Send a new code
        </button>
      </p>
    </div>
  )
}
