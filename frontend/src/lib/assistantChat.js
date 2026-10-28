// Small pure helpers for the assistant chat (kept out of the component so they can be tested).

export const MAX_MESSAGES = 12 // the server refuses longer conversations
export const MAX_CHARS = 800

export const SUGGESTIONS = [
  'Find me a cycle under ₹2,000',
  "What's closing soon?",
  'Show me the cheapest calculators',
  'How am I doing on my bids?',
]

/** What to send to the server: only role and text, the latest turns, each within the size limit. */
export function toApiMessages(messages) {
  return messages
    .filter((m) => (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string' && m.content.trim())
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_CHARS) }))
    .slice(-MAX_MESSAGES)
}

/** True when the draft can be sent. */
export const canSend = (draft, busy) => !busy && draft.trim().length > 0 && draft.length <= MAX_CHARS

/** Apply a proposal state change to one message, leaving the others untouched. */
export function withProposalState(messages, messageIndex, listingId, state) {
  return messages.map((m, i) =>
    i === messageIndex ? { ...m, proposalStates: { ...(m.proposalStates ?? {}), [listingId]: state } } : m,
  )
}

/** The model sometimes slips in markdown. The chat shows plain text, so remove the symbols and keep the words. */
export function plainText(text) {
  return String(text ?? '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
}
