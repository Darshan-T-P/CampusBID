import { describe, expect, it } from 'vitest'
import { bidOutcome, groupBids } from './myBids'
import { SALE_ACTIONS, actionsFor, groupListings } from './sale'

describe('actionsFor', () => {
  it('offers the right buttons for each state', () => {
    expect(actionsFor('pending_approval')).toEqual(['approve', 'reject'])
    expect(actionsFor('reserved')).toEqual(['handover', 'pickup-failed'])
    expect(actionsFor('active')).toEqual(['cancel'])
  })
  it('offers nothing once a listing is final', () => {
    for (const s of ['completed', 'failed_pickup', 'rejected', 'unsold', 'cancelled']) expect(actionsFor(s)).toEqual([])
  })
  it('every offered action is defined, and destructive ones ask for confirmation', () => {
    for (const s of ['pending_approval', 'reserved', 'active']) for (const a of actionsFor(s)) expect(SALE_ACTIONS[a]).toBeTruthy()
    for (const a of ['reject', 'pickup-failed', 'cancel', 'handover']) expect(SALE_ACTIONS[a].confirm).toBeTruthy()
    expect(SALE_ACTIONS.approve.confirm).toBeUndefined()
    expect(SALE_ACTIONS.reject.askReason).toBe(true)
  })
})

describe('groupListings', () => {
  const items = ['active', 'completed', 'pending_approval', 'reserved', 'cancelled', 'active'].map((status, id) => ({ id, status }))
  it('orders sections by what needs attention and keeps order inside them', () => {
    const groups = groupListings(items)
    expect(groups.map((g) => g.key)).toEqual(['decide', 'handover', 'open', 'finished'])
    expect(groups[2].items.map((i) => i.id)).toEqual([0, 5])
    expect(groups[3].items.map((i) => i.status)).toEqual(['completed', 'cancelled'])
  })
  it('drops empty sections and handles no listings', () => {
    expect(groupListings([{ id: 1, status: 'active' }]).map((g) => g.key)).toEqual(['open'])
    expect(groupListings([])).toEqual([])
  })
})

const row = (status, is_leading, extra = {}) => ({
  listing: { id: 1, status, price: 700, ...extra },
  my_highest_bid: 650,
  is_leading,
})

describe('bidOutcome', () => {
  it('tells an active bidder if they lead or were outbid', () => {
    expect(bidOutcome(row('active', true))).toMatchObject({ section: 'active', tone: 'success' })
    const outbid = bidOutcome(row('active', false))
    expect(outbid).toMatchObject({ section: 'active', tone: 'warn' })
    expect(outbid.text).toContain('₹700')
    expect(outbid.text).toContain('₹650')
  })
  it('follows a win through the sale', () => {
    expect(bidOutcome(row('pending_approval', true))).toMatchObject({ section: 'won', tone: 'info' })
    expect(bidOutcome(row('reserved', true))).toMatchObject({ section: 'won', tone: 'success' })
    expect(bidOutcome(row('completed', true)).text).toContain('₹700')
  })
  it('explains losses and failed sales', () => {
    expect(bidOutcome(row('pending_approval', false)).section).toBe('ended')
    expect(bidOutcome(row('reserved', false)).text).toMatch(/another bidder/)
    expect(bidOutcome(row('rejected', true))).toMatchObject({ section: 'ended', tone: 'danger' })
    expect(bidOutcome(row('failed_pickup', true))).toMatchObject({ section: 'ended', tone: 'danger' })
    expect(bidOutcome(row('cancelled', true)).text).toMatch(/cancelled/)
    expect(bidOutcome(row('cancelled', false)).text).toMatch(/cancelled/)
  })
  it('never leaves a status without a message', () => {
    for (const s of ['active', 'pending_approval', 'reserved', 'completed', 'failed_pickup', 'rejected', 'unsold', 'cancelled'])
      for (const lead of [true, false]) expect(bidOutcome(row(s, lead)).text).toBeTruthy()
  })
})

describe('groupBids', () => {
  it('groups into active / won / ended', () => {
    const groups = groupBids([row('active', true), row('pending_approval', true), row('cancelled', true), row('active', false)])
    expect(groups.map((g) => [g.key, g.entries.length])).toEqual([['active', 2], ['won', 1], ['ended', 1]])
  })
  it('drops empty sections', () => {
    expect(groupBids([row('active', true)]).map((g) => g.key)).toEqual(['active'])
    expect(groupBids([])).toEqual([])
  })
})
