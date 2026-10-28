import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, mediaUrl } from '../api/client'
import { errorMessage } from '../api/errors'
import { Countdown } from '../components/Countdown'
import { StatusBadge } from '../components/StatusBadge'
import { groupBids } from '../lib/myBids'

export function MyBids() {
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
