import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, mediaUrl } from '../api/client'
import { errorMessage } from '../api/errors'
import { ContactCard } from '../components/ContactCard'
import { Countdown } from '../components/Countdown'
import { Icon } from '../components/Icon'
import { StatusBadge } from '../components/StatusBadge'
import { formatRupees } from '../lib/format'
import { groupBids } from '../lib/myBids'
import { usePageTitle } from '../hooks/usePageTitle'

export function MyBids() {
  usePageTitle('My bids')
  const autoQuery = useQuery({ queryKey: ['my-auto-bids'], queryFn: () => api('/me/auto-bids'), refetchInterval: 10_000 })
  const query = useQuery({
    queryKey: ['my-bids'],
    queryFn: () => api('/me/bids'),
    refetchInterval: 10_000, // outbid / won while this page is open
  })

  if (query.isPending) return <p className="muted center">Loading your bids…</p>
  if (query.isError) {
    return (
      <p className="error" role="alert">
        {errorMessage(query.error)}{' '}
        <button type="button" className="link-button" onClick={() => query.refetch()}>
          Try again
        </button>
      </p>
    )
  }

  const groups = groupBids(query.data)
  const maxByListing = new Map((autoQuery.data ?? []).map((a) => [a.listing_id, a.max_amount]))

  return (
    <section>
      <h1>My bids</h1>
      {query.data.length === 0 ? (
        <div className="empty card">
          <p>You haven't bid on anything yet.</p>
          <Link to="/" className="btn btn-primary">
            Browse auctions
          </Link>
        </div>
      ) : (
        groups.map((group) => (
          <div key={group.key} className="group">
            <h2>
              {group.title} <span className="muted">({group.entries.length})</span>
            </h2>
            <ul className="rows">
              {group.entries.map(({ row, outcome }) => (
                <li key={row.listing.id} className="row-card">
                  <Link to={`/listings/${row.listing.id}`} className="row-thumb" aria-hidden="true" tabIndex={-1}>
                    {row.listing.thumbnail ? <img src={mediaUrl(row.listing.thumbnail)} alt="" loading="lazy" /> : <span>No photo</span>}
                  </Link>
                  <div className="row-main">
                    <div className="row-title">
                      <Link to={`/listings/${row.listing.id}`}>{row.listing.title}</Link>
                      <StatusBadge status={row.listing.status} />
                    </div>
                    <p className={`outcome outcome-${outcome.tone}`}>{outcome.text}</p>
                    {outcome.section === 'won' && row.listing.handover_spot && ['reserved', 'pending_approval'].includes(row.listing.status) && (
                      <p className="muted small">
                        <Icon name="pin" size={13} /> Meet at <strong>{row.listing.handover_spot}</strong>
                      </p>
                    )}
                    {outcome.section === 'won' && row.listing.status === 'reserved' && <ContactCard listingId={row.listing.id} compact />}
                    {row.listing.status === 'active' && maxByListing.has(row.listing.id) && (
                      <p className="muted small">Automatic bidding up to {formatRupees(maxByListing.get(row.listing.id))}</p>
                    )}
                    {row.listing.status === 'active' && (
                      <p className="muted small">
                        <Countdown closesAt={row.listing.closes_at} /> · {row.listing.bid_count} {row.listing.bid_count === 1 ? 'bid' : 'bids'} ·{' '}
                        <Link to={`/listings/${row.listing.id}`}>{row.is_leading ? 'View' : 'Bid again'}</Link>
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  )
}
