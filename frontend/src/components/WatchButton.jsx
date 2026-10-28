import { useLocation, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { useToggleWatch } from '../hooks/useWatchlist'
import { Icon } from './Icon'

/**
 * Save an auction to the watchlist. `variant="icon"` is the round button on a card; `variant="full"` is the
 * labelled button on the listing page. Visitors are sent to sign in; sellers don't see it on their own items.
 */
export function WatchButton({ listingId, sellerId, variant = 'full' }) {
  const { isSignedIn, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const { saved, toggle, pending, error } = useToggleWatch(listingId)

  if (isSignedIn && user && user.id === sellerId) return null

  function onClick(event) {
    event.preventDefault() // the card around it is a link
    event.stopPropagation()
    if (!isSignedIn) return navigate('/login', { state: { from: location.pathname + location.search } })
    toggle()
  }

  const label = saved ? 'Remove from watchlist' : 'Save to watchlist'
  if (variant === 'icon') {
    return (
      <button type="button" className={`watch-fab ${saved ? 'is-saved' : ''}`} onClick={onClick} disabled={pending} aria-pressed={saved} aria-label={label} title={error ? errorMessage(error) : label}>
        <Icon name="bookmark" size={17} filled={saved} />
      </button>
    )
  }
  return (
    <span className="watch-wrap">
      <button type="button" className={`btn btn-ghost btn-sm watch-btn ${saved ? 'is-saved' : ''}`} onClick={onClick} disabled={pending} aria-pressed={saved}>
        <Icon name="bookmark" size={15} filled={saved} /> {saved ? 'Saved' : 'Save'}
      </button>
      {error && <small className="field-error" role="alert">{errorMessage(error)}</small>}
    </span>
  )
}
