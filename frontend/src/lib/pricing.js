// Price suggestions for sellers: what similar items sold for, in words.

import { conditionLabel, formatRupees } from './format'

/** True when the server had enough past sales to say anything. */
export const hasSuggestion = (s) => Boolean(s && s.count >= 3 && s.median != null)

/** Which group of past sales the numbers come from, e.g. "Similar items". */
export function basisLabel(s, condition) {
  if (s.basis === 'similar') return 'Similar items'
  if (s.basis === 'condition') return `${conditionLabel(condition)} items in this category`
  return 'Items in this category'
}

/** Two short lines for the Sell page. Returns null when there is nothing honest to say. */
export function describeSuggestion(s, condition) {
  if (!hasSuggestion(s)) return null
  const range = s.low === s.high ? formatRupees(s.median) : `${formatRupees(s.low)} to ${formatRupees(s.high)}`
  return {
    sold: `${basisLabel(s, condition)} sold for ${range} (typically ${formatRupees(s.median)}, from ${s.count} sales).`,
    start: `A starting price around ${formatRupees(s.suggested_start)} tends to invite early bids.`,
  }
}
