// "Someone already asked something like this": a gentle hint before a duplicate question is posted.
// Plain word overlap is enough here: it only has to catch the obvious repeats, and the buyer decides.

const STOP_WORDS = new Set([
  'a', 'an', 'the', 'is', 'it', 'are', 'was', 'were', 'be', 'does', 'do', 'did', 'has', 'have', 'any', 'there', 'this', 'that',
  'of', 'on', 'in', 'at', 'to', 'for', 'and', 'or', 'with', 'about', 'you', 'your', 'can', 'could', 'would', 'will', 'i', 'me', 'my', 'please',
])

const MIN_WORDS = 2 // a one-word question like "price?" is too vague to call a repeat
export const SIMILARITY_THRESHOLD = 0.6

/** Lower-case words with punctuation and filler words removed, and a trailing "s" folded away ("gears" ~ "gear"). */
export function significantWords(text) {
  return [
    ...new Set(
      String(text ?? '')
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, ' ')
        .split(/\s+/)
        .filter((w) => w && !STOP_WORDS.has(w))
        .map((w) => (w.length > 3 && w.endsWith('s') ? w.slice(0, -1) : w)),
    ),
  ]
}

/** How alike two questions are, 0 to 1: shared words over the words of the shorter one. */
export function similarity(a, b) {
  const wa = significantWords(a)
  const wb = significantWords(b)
  if (wa.length < MIN_WORDS || wb.length < MIN_WORDS) return 0
  const shared = wa.filter((w) => wb.includes(w)).length
  return shared / Math.min(wa.length, wb.length)
}

/** The existing question (visible ones only) that best matches `text`, or null when nothing is close enough. */
export function findSimilarQuestion(text, questions) {
  let best = null
  let bestScore = 0
  for (const q of questions) {
    if (q.hidden) continue
    const score = similarity(text, q.question_text)
    if (score >= SIMILARITY_THRESHOLD && score > bestScore) {
      best = q
      bestScore = score
    }
  }
  return best
}
