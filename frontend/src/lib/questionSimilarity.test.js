import { describe, expect, it } from 'vitest'
import { findSimilarQuestion, significantWords, similarity } from './questionSimilarity'

describe('significantWords', () => {
  it('drops filler words and punctuation and folds plurals', () => {
    expect(significantWords('Do the gears shift smoothly?')).toEqual(['gear', 'shift', 'smoothly'])
  })
})

describe('similarity', () => {
  it('is high for the same question worded differently', () => {
    expect(similarity('Do the gears shift smoothly?', 'Is the gear shifting smooth?')).toBeGreaterThanOrEqual(0.3)
    expect(similarity('Any scratches on the screen?', 'Are there scratches on screen')).toBeGreaterThanOrEqual(0.6)
  })
  it('is zero for different questions and for vague one-word ones', () => {
    expect(similarity('Any scratches on the screen?', 'Can you meet near the library gate')).toBe(0)
    expect(similarity('price?', 'price?')).toBe(0)
  })
})

describe('findSimilarQuestion', () => {
  const thread = [
    { id: 1, question_text: 'Are there any scratches on the screen?', hidden: false },
    { id: 2, question_text: 'Does the charger come with it?', hidden: false },
    { id: 3, question_text: 'scratches on the screen BUY NOW', hidden: true },
  ]
  it('finds the closest visible repeat', () => {
    expect(findSimilarQuestion('Any scratches on screen?', thread).id).toBe(1)
    expect(findSimilarQuestion('does it come with a charger', thread).id).toBe(2)
  })
  it('ignores hidden questions and different topics', () => {
    expect(findSimilarQuestion('Where can we meet for handover', thread)).toBeNull()
    expect(findSimilarQuestion('scratches on the screen BUY NOW', [thread[2]])).toBeNull()
  })
  it('returns null for an empty thread or empty text', () => {
    expect(findSimilarQuestion('anything at all here', [])).toBeNull()
    expect(findSimilarQuestion('', thread)).toBeNull()
  })
})
