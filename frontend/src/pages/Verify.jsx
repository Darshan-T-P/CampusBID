import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { usePageTitle } from '../hooks/usePageTitle'

export function Verify() {
  usePageTitle('Verify your email')
  const { user, refreshUser } = useAuth()
  const navigate = useNavigate()

  const [code, setCode] = useState('')
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(false)

  if (user?.is_verified) return <Navigate to="/" replace />

  async function onSubmit(event) {
    event.preventDefault()
    setError(null)
    setInfo(null)
    setBusy(true)
    try {
      await api('/auth/verify', { method: 'POST', body: { code } })
      await refreshUser()
      navigate('/', { replace: true })
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  async function resend() {
    setError(null)
    setInfo(null)
    try {
      await api('/auth/resend-code', { method: 'POST' })
      setInfo('A new code is on its way.')
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <div className="card auth-card">
      <h1>Verify your email</h1>
      <p className="muted">
        We sent a 6-digit code to <strong>{user?.email}</strong>. Codes expire after 10 minutes.
      </p>
      <form onSubmit={onSubmit} className="form">
        <label>
          Code
          <input
            className="code-input"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="\d{6}"
            maxLength={6}
            required
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
          />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {info && <p className="success">{info}</p>}
        <button className="btn btn-primary" disabled={busy || code.length !== 6}>
          {busy ? 'Checking…' : 'Verify'}
        </button>
      </form>
      <p className="muted">
        Didn't get it?{' '}
        <button type="button" className="link-button" onClick={resend}>
          Send a new code
        </button>
      </p>
    </div>
  )
}
