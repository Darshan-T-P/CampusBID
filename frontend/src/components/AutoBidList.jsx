import { formatRupees } from '../lib/format'

/** Everyone's standing maximums on an auction. Public by design: nothing about bidding is private. */
export function AutoBidList({ autoBids }) {
  if (autoBids.length === 0) {
    return <p className="muted">No one has set an automatic maximum on this auction.</p>
  }
  return (
    <ul className="history auto-list">
      {autoBids.map((a, i) => (
        <li key={`${a.bidder_name}-${i}`}>
          <span className="history-amount">{formatRupees(a.max_amount)}</span>
          <span className="history-who">{a.bidder_name}</span>
          <span className="muted small">maximum</span>
        </li>
      ))}
    </ul>
  )
}
