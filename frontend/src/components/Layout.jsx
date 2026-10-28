import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'

export function Layout() {
  const { user, isSignedIn, logout } = useAuth()

  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <Link to="/" className="brand">
            CampusBid
          </Link>
          <nav className="nav">
            <NavLink to="/" end>
              Browse
            </NavLink>
            <NavLink to="/sell">Sell an item</NavLink>
          </nav>
          <div className="topbar-right">
            {isSignedIn ? (
              <>
                {user && <span className="who">{user.display_name}</span>}
                <button className="btn btn-ghost" onClick={logout}>
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
