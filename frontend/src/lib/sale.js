// What a seller can do with a listing, depending on its state. The backend enforces all of this too
// (wrong state -> 409); this decides which buttons to show.

export const SALE_ACTIONS = {
  approve: {
    label: 'Approve sale',
    style: 'primary',
    success: 'Sale approved. The winner has been told.',
  },
  reject: {
    label: 'Reject',
    style: 'danger',
    confirm: 'Reject the winning bid? The winner will be told it was rejected.',
    askReason: true,
    success: 'Sale rejected. The winner has been told.',
  },
  handover: {
    label: 'Mark handed over',
    style: 'primary',
    confirm: 'Confirm the item has been handed over?',
    success: 'Marked as completed.',
  },
  'pickup-failed': {
    label: "Winner didn't collect",
    style: 'danger',
    confirm: 'Record that the winner never collected the item?',
    success: 'Recorded as a failed pickup.',
  },
  cancel: {
    label: 'Cancel listing',
    style: 'danger',
    confirm: 'Cancel this listing? Everyone who bid will be told.',
    success: 'Listing cancelled.',
  },
}

/** Which actions apply to a listing in this status, in display order. */
export function actionsFor(status) {
  switch (status) {
    case 'pending_approval':
      return ['approve', 'reject']
    case 'reserved':
      return ['handover', 'pickup-failed']
    case 'active':
      return ['cancel']
    default:
      return [] // completed, rejected, unsold, cancelled, failed_pickup are final
  }
}

const SECTIONS = [
  { key: 'decide', title: 'Needs your decision', hint: 'The auction ended with a winner. Approve or reject the sale.', statuses: ['pending_approval'] },
  { key: 'handover', title: 'Awaiting handover', hint: 'Approved. Meet the winner, then confirm.', statuses: ['reserved'] },
  { key: 'open', title: 'Open auctions', hint: null, statuses: ['active'] },
  { key: 'finished', title: 'Finished', hint: null, statuses: ['completed', 'failed_pickup', 'rejected', 'unsold', 'cancelled'] },
]

/** Split a seller's listings into titled sections, keeping order, dropping empty ones. */
export function groupListings(items) {
  return SECTIONS.map((section) => ({
    ...section,
    items: items.filter((item) => section.statuses.includes(item.status)),
  })).filter((section) => section.items.length > 0)
}
