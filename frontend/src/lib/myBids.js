// What a bid means to the person who placed it, in plain words. `row` is one entry from GET /me/bids:
//   { listing: <card>, my_highest_bid, is_leading }
// `is_leading` means "my bid is the one the listing currently points at": the top bid while the
// auction runs, and the winning bid once it has ended.
import { formatRupees } from './format'

export const BID_SECTIONS = [
  { key: 'active', title: 'Active bids' },
  { key: 'won', title: 'Won' },
  { key: 'ended', title: 'Ended' },
]

/** -> { section: 'active' | 'won' | 'ended', tone: 'success' | 'warn' | 'info' | 'muted' | 'danger', text } */
export function bidOutcome(row) {
  const { listing, is_leading: leading, my_highest_bid: mine } = row
  const lost = { section: 'ended', tone: 'muted', text: "The auction ended and you didn't win." }

  switch (listing.status) {
    case 'active':
      return leading
        ? { section: 'active', tone: 'success', text: `You're the highest bidder at ${formatRupees(mine)}.` }
        : {
            section: 'active',
            tone: 'warn',
            text: `You've been outbid. The price is now ${formatRupees(listing.price)}; your best bid was ${formatRupees(mine)}.`,
          }
    case 'pending_approval':
      return leading
        ? { section: 'won', tone: 'info', text: 'You won! Waiting for the seller to approve the sale.' }
        : lost
    case 'reserved':
      return leading
        ? { section: 'won', tone: 'success', text: 'The seller approved your bid. Arrange the handover with them.' }
        : { section: 'ended', tone: 'muted', text: 'Sold to another bidder.' }
    case 'completed':
      return leading
        ? { section: 'won', tone: 'success', text: `You bought this for ${formatRupees(listing.price)}.` }
        : { section: 'ended', tone: 'muted', text: 'Sold to another bidder.' }
    case 'failed_pickup':
      return leading
        ? { section: 'ended', tone: 'danger', text: 'The pickup did not happen, so the sale fell through.' }
        : { section: 'ended', tone: 'muted', text: 'The sale to another bidder fell through.' }
    case 'rejected':
      return leading ? { section: 'ended', tone: 'danger', text: 'The seller rejected the sale.' } : lost
    case 'cancelled':
      return { section: 'ended', tone: 'danger', text: 'The seller cancelled this listing.' }
    default:
      return lost
  }
}

/** Split bids into the three sections, keeping order and attaching each outcome. Empty sections are dropped. */
export function groupBids(rows) {
  const withOutcome = rows.map((row) => ({ row, outcome: bidOutcome(row) }))
  return BID_SECTIONS.map((section) => ({
    ...section,
    entries: withOutcome.filter((entry) => entry.outcome.section === section.key),
  })).filter((section) => section.entries.length > 0)
}
