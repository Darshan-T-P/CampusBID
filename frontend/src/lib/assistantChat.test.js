import { describe, expect, it } from 'vitest'
import { MAX_CHARS, MAX_MESSAGES, canSend, plainText, toApiMessages, withProposalState } from './assistantChat'

describe('toApiMessages', () => {
  it('sends only role and text, never the cards or states', () => {
    const out = toApiMessages([{ role: 'assistant', content: 'hi', listings: [{ id: 1 }], proposals: [{}], proposalStates: { 1: 'done' } }])
    expect(out).toEqual([{ role: 'assistant', content: 'hi' }])
  })
  it('drops empty and unknown-role entries', () => {
    expect(toApiMessages([{ role: 'system', content: 'x' }, { role: 'user', content: '   ' }, { role: 'user', content: 'ok' }])).toEqual([{ role: 'user', content: 'ok' }])
  })
  it('keeps only the latest turns and trims long text to the server limit', () => {
    const many = Array.from({ length: 20 }, (_, i) => ({ role: i % 2 ? 'assistant' : 'user', content: `m${i}` }))
    const out = toApiMessages(many)
    expect(out).toHaveLength(MAX_MESSAGES)
    expect(out.at(-1).content).toBe('m19')
    expect(toApiMessages([{ role: 'user', content: 'x'.repeat(MAX_CHARS + 50) }])[0].content).toHaveLength(MAX_CHARS)
  })
})

describe('canSend', () => {
  it('needs text, no request in flight, and a draft within the limit', () => {
    expect(canSend('find a lamp', false)).toBe(true)
    expect(canSend('   ', false)).toBe(false)
    expect(canSend('hi', true)).toBe(false)
    expect(canSend('x'.repeat(MAX_CHARS + 1), false)).toBe(false)
  })
})

describe('withProposalState', () => {
  it('changes one proposal on one message only', () => {
    const before = [{ role: 'assistant', content: 'a' }, { role: 'assistant', content: 'b', proposalStates: { 7: 'pending' } }]
    const after = withProposalState(before, 1, 9, 'done')
    expect(after[1].proposalStates).toEqual({ 7: 'pending', 9: 'done' })
    expect(after[0]).toBe(before[0])
    expect(before[1].proposalStates).toEqual({ 7: 'pending' }) // not mutated
  })
})

describe('plainText', () => {
  it('removes markdown symbols but keeps the words', () => {
    expect(plainText('- **Hero cycle** - ₹1,800, `good`')).toBe('- Hero cycle - ₹1,800, good')
    expect(plainText('## Picks\n__one__')).toBe('Picks\none')
  })
  it('leaves ordinary text, rupee signs and a lone asterisk alone', () => {
    expect(plainText('It costs ₹2,000 * 2 bids')).toBe('It costs ₹2,000 * 2 bids')
    expect(plainText(null)).toBe('')
  })
})
