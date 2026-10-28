import { formatRupees } from '../lib/format'
import { defaultMinRaise } from '../lib/raise'

/**
 * Explains the minimum raise to a seller, in plain words. They don't type it: the app works it out from the starting
 * price (`current` is the value an existing listing already has, shown while its price is unchanged).
 */
export function RaiseNote({ startingPrice, current = null }) {
  const raise = current ?? (startingPrice ? defaultMinRaise(startingPrice) : null)
  return (
    <div className="raise-note" role="note">
      <strong>{raise ? `Bids will rise by at least ${formatRupees(raise)}` : 'The minimum raise is set for you'}</strong>
      <span>
        {raise
          ? 'The app sets this automatically from your starting price, so the bidding keeps moving without tiny ₹1 bids. '
          : 'Enter a starting price to see it. It is worked out automatically (about 5% of the starting price). '}
        Buyers can always bid more, and anyone using automatic bidding can choose a bigger raise.
      </span>
    </div>
  )
}
