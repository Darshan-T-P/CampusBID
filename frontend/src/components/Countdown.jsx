import { useNow } from '../hooks/useNow'
import { formatRemaining, urgencyOf } from '../lib/format'

/** Live time left until `closesAt`, measured against the SERVER's clock. Cosmetic only: the
 *  backend alone decides whether a bid is on time. */
export function Countdown({ closesAt, className = '' }) {
  const now = useNow()
  const remaining = Date.parse(closesAt) - now
  return (
    <span className={`countdown countdown-${urgencyOf(remaining)} ${className}`} title={new Date(closesAt).toLocaleString()}>
      {remaining > 0 ? `${formatRemaining(remaining)} left` : 'Ended'}
    </span>
  )
}
