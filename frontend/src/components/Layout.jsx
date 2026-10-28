import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { NotificationBell } from './NotificationBell'

export function Layout() {
  const { user, isSignedIn, logout } = useAuth()

  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <Link to="/" className="brand">
            <span className="brand-badge" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
              </svg>
            </span>
            <span className="brand-name">Re<span className="brand-accent">lay</span></span>
          </Link>
          <nav className="nav">
            <NavLink to="/" end>
              Browse
            </NavLink>
            <NavLink to="/sell">Sell an item</NavLink>
            {isSignedIn && <NavLink to="/my/listings">My listings</NavLink>}
            {isSignedIn && <NavLink to="/my/bids">My bids</NavLink>}
          </nav>
          <div className="topbar-right">
            {isSignedIn ? (
              <>
                <NotificationBell />
                {user && (
                  <div className="user-pill" title={user.email}>
                    <span className="user-avatar">{user.display_name?.charAt(0).toUpperCase() || 'U'}</span>
                    <span className="who">{user.display_name}</span>
                  </div>
                )}
                <button className="btn btn-ghost btn-sm" onClick={logout}>
                  Sign out
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn btn-ghost">
                  Sign in
                </Link>
                <Link to="/register" className="btn btn-primary">
                  Register
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {user && !user.is_verified && (
        <div className="banner" role="status">
          <div className="container">
            Verify your campus email to list items or bid. <Link to="/verify">Enter your code</Link>
          </div>
        </div>
      )}

      <main className="container page">
        <Outlet />
      </main>
    </>
  )
}
