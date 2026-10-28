import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { PasswordField } from '../components/PasswordField'
import { usePageTitle } from '../hooks/usePageTitle'

export function Login() {
  usePageTitle('Sign in')
  const { login, isSignedIn, user, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from ?? '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  // Signing in flips isSignedIn before onSubmit navigates, so wait for the profile and route by verification.
  if (isSignedIn) return loading ? null : <Navigate to={user && !user.is_verified ? '/verify' : from} replace />

  async function onSubmit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const result = await login(email, password)
      navigate(result.is_verified ? from : '/verify', { replace: true })
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  return (
    <div className="card auth-card">
      <h1>Sign in</h1>
      <form onSubmit={onSubmit} className="form">
        <div className="form-field">
          <label htmlFor="login-email">Campus email</label>
          <input id="login-email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <PasswordField
          id="login-password"
          label="Password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="btn btn-primary" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <p className="muted">
        <Link to="/forgot-password">Forgot your password?</Link>
      </p>
      <p className="muted">
        New here? <Link to="/register">Create an account</Link>
      </p>
    </div>
  )
}
