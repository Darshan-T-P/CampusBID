import { useNow } from '../hooks/useNow'
import { formatRemaining, urgencyOf } from '../lib/format'

/** Live time left until `closesAt`, measured against the SERVER's clock. Cosmetic only: the
 *  backend alone decides whether a bid is on time. */
export function Countdown({ closesAt, className = '' }) {
  const now = useNow()
  const remaining = Date.parse(closesAt) - now
  const urgency = urgencyOf(remaining)
  const isLive = remaining > 0

  return (
    <span className={`countdown countdown-${urgency} ${className}`} title={new Date(closesAt).toLocaleString()}>
      {isLive && <span className={`countdown-pulse countdown-pulse-${urgency}`} aria-hidden="true" />}
      {isLive ? `${formatRemaining(remaining)} left` : 'Ended'}
    </span>
  )
}
