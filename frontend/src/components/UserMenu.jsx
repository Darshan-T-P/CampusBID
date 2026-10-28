import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Icon } from './Icon'

/** The round avatar in the top bar. Opens a menu: profile, my listings, my bids, and sign out. */
export function UserMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const wrap = useRef(null)
  const button = useRef(null)

  // Close on an outside click or Escape (Escape returns focus to the avatar).
  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => wrap.current && !wrap.current.contains(e.target) && setOpen(false)
    const onKey = (e) => {
      if (e.key === 'Escape') {
        setOpen(false)
        button.current?.focus()
      }
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const name = user?.display_name ?? 'Account'
  const initial = name.charAt(0).toUpperCase() || 'U'
  const close = () => setOpen(false)

  return (
    <div className="user-menu" ref={wrap}>
      <button
        ref={button}
        type="button"
        className="avatar-btn"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${name}`}
        title={name}
      >
        <span className="avatar">{initial}</span>
        <Icon name="chevron" size={14} className="avatar-chevron" />
      </button>

      {open && (
        <div className="menu" role="menu" aria-label="Account">
          <div className="menu-head">
            <span className="avatar avatar-lg" aria-hidden="true">{initial}</span>
            <div className="menu-who">
              <strong>{name}</strong>
              {user?.email && <small className="muted">{user.email}</small>}
            </div>
          </div>
          <Link role="menuitem" className="menu-item" to="/profile" onClick={close}>
            <Icon name="user" size={17} /> Profile
          </Link>
          <Link role="menuitem" className="menu-item" to="/my/listings" onClick={close}>
            <Icon name="tag" size={17} /> My listings
          </Link>
          <Link role="menuitem" className="menu-item" to="/my/bids" onClick={close}>
            <Icon name="gavel" size={17} /> My bids
          </Link>
          <div className="menu-sep" role="separator" />
          <button
            type="button"
            role="menuitem"
            className="menu-item menu-item-danger"
            onClick={() => {
              close()
              logout()
            }}
          >
            <Icon name="logout" size={17} /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}
