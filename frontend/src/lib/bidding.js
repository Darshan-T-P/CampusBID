// Bid-form rules and status wording. The backend is the real judge of every bid; these just give
// instant feedback before a request is sent.
import { formatRupees } from './format'

/** "1,200" / " 450 " / "12.5" / "abc" -> a positive whole number, or null if it isn't one. */
export function parseAmount(text) {
  const clean = String(text).trim().replace(/,/g, '')
  if (!/^\d+$/.test(clean)) return null
  const n = Number(clean)
  return Number.isSafeInteger(n) && n > 0 ? n : null
}

/** Returns a message to show the bidder, or null if the amount looks valid. */
export function validateBid(text, minNextBid) {
  if (String(text).trim() === '') return 'Enter an amount'
  const amount = parseAmount(text)
  if (amount === null) return 'Enter a whole number of rupees'
  if (minNextBid != null && amount < minNextBid) return `The minimum bid is ${formatRupees(minNextBid)}`
  return null
}

// tone drives the badge colour: success | warn | info | muted | danger
export const STATUS_INFO = {
  active: { label: 'Open for bids', tone: 'success' },
  pending_approval: { label: 'Ended · awaiting seller', tone: 'warn' },
  reserved: { label: 'Sold · awaiting handover', tone: 'info' },
  completed: { label: 'Sold', tone: 'muted' },
  failed_pickup: { label: 'Pickup failed', tone: 'danger' },
  rejected: { label: 'Sale rejected', tone: 'danger' },
  unsold: { label: 'Ended · no bids', tone: 'muted' },
  cancelled: { label: 'Cancelled', tone: 'danger' },
}

export const statusInfo = (status) => STATUS_INFO[status] ?? { label: status, tone: 'muted' }

/** One plain sentence about what happened to a closed listing, for the page banner. */
export function closedMessage(listing) {
  const price = listing.current_price != null ? formatRupees(listing.current_price) : null
  switch (listing.status) {
    case 'pending_approval':
      return `The auction has ended. ${listing.leading_bidder} is the top bidder at ${price}, waiting for the seller to approve the sale.`
    case 'reserved':
      return `The seller approved ${listing.leading_bidder}'s bid of ${price}. The handover is being arranged.`
    case 'completed':
      return `Sold to ${listing.leading_bidder} for ${price}.`
    case 'failed_pickup':
      return `The sale to ${listing.leading_bidder} did not complete: the item was not collected.`
    case 'rejected':
      return 'The seller rejected the winning bid, so this item was not sold.'
    case 'unsold':
      return 'The auction ended with no bids.'
    case 'cancelled':
      return 'The seller cancelled this listing.'
    default:
      return null
  }
}

/**
 * The "raise by" an automatic bidder typed. Blank means "use the auction's minimum raise" ({ value: null }).
 * Otherwise a whole number of rupees, at least the auction's minimum raise.
 */
export function parseRaise(text, minRaise) {
  if (String(text ?? '').trim() === '') return { value: null }
  const n = parseAmount(text)
  if (n === null) return { error: 'Enter a whole number of rupees for the raise' }
  if (minRaise != null && n < minRaise) return { error: `The raise must be at least ${formatRupees(minRaise)}, the minimum raise` }
  return { value: n }
}
