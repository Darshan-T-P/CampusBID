import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Icon } from './Icon'
import { NotificationBell } from './NotificationBell'

const icon = (d) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {d}
  </svg>
)
const ICONS = {
  browse: icon(<><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V20h14V9.5" /></>),
  sell: icon(<><circle cx="12" cy="12" r="9" /><path d="M12 8v8M8 12h8" /></>),
  listings: icon(<><path d="M4 6h16M4 12h16M4 18h10" /></>),
  bids: icon(<><path d="m14 13-7.5 7.5a2.1 2.1 0 0 1-3-3L11 10" /><path d="m16 16 6-6M8 8l6-6M9 7l8 8M21 11l-8-8" /></>),
  signin: icon(<><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3" /></>),
}

export function Layout() {
  const { user, isSignedIn, logout } = useAuth()

  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <Link to="/" className="brand">
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

      {/* Phones: the top links don't fit, so navigation moves to a thumb-reach bar at the bottom. */}
      <nav className="tabbar" aria-label="Main">
        <NavLink to="/" end>
          {ICONS.browse}
          <span>Browse</span>
        </NavLink>
        {isSignedIn ? (
          <>
            <NavLink to="/sell">
              {ICONS.sell}
              <span>Sell</span>
            </NavLink>
            <NavLink to="/my/listings">
              {ICONS.listings}
              <span>Listings</span>
            </NavLink>
            <NavLink to="/my/bids">
              {ICONS.bids}
              <span>My bids</span>
            </NavLink>
          </>
        ) : (
          <NavLink to="/login">
            {ICONS.signin}
            <span>Sign in</span>
          </NavLink>
        )}
      </nav>

      <footer className="footer">
        <div className="container footer-inner">
          <div className="footer-col">
            <span className="brand-name">Re<span className="brand-accent">lay</span></span>
            <p className="footer-desc">
              A timed auction marketplace for campus. Students buy and sell used essentials at fair prices.
            </p>
          </div>
          <div className="footer-links">
            <Link to="/">Browse auctions</Link>
            <Link to="/sell">List an item</Link>
            {isSignedIn && <Link to="/my/listings">My listings</Link>}
            {isSignedIn && <Link to="/my/bids">My bids</Link>}
          </div>
          <div className="footer-badge">
            <span className="footer-badge-title"><Icon name="shield" size={16} /> Verified campus students only</span>
            <small className="muted">Items are handed over in person on campus</small>
          </div>
        </div>
      </footer>
    </>
  )
}
