import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './useAuth'

/** Wrap protected routes: signed-out visitors are sent to the login page and brought back after. */
export function RequireAuth() {
  const { isSignedIn, loading, user } = useAuth()
  const location = useLocation()

  if (loading) return <p className="muted center">Loading…</p>
  // No token, or the token turned out to belong to nobody (expired / deleted account).
  if (!isSignedIn || !user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}
