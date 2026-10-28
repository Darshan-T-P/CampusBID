import { formatRupees } from '../lib/format'

const when = (iso) => new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })

/** The public bid history, newest (= highest) first. Shows display names only. */
export function BidHistory({ bids }) {
  if (bids.length === 0) {
    return <p className="muted">No bids yet. Be the first!</p>
  }
  return (
    <ol className="history">
      {bids.map((bid, i) => (
        <li key={bid.id} className={i === 0 ? 'history-top' : ''}>
          <span className="history-amount">{formatRupees(bid.amount)}</span>
          <span className="history-who">
            {bid.bidder_name}
            {i === 0 && <span className="chip chip-lead">Highest</span>}
          </span>
          <time className="muted small" dateTime={bid.created_at}>
            {when(bid.created_at)}
          </time>
        </li>
      ))}
    </ol>
  )
}
