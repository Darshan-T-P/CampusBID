import { statusInfo } from '../lib/bidding'

export function StatusBadge({ status }) {
  const { label, tone } = statusInfo(status)
  return <span className={`badge badge-${tone}`}>{label}</span>
}
