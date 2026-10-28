import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { usePageTitle } from '../hooks/usePageTitle'
import { useNow } from '../hooks/useNow'
import { timeAgo } from '../lib/format'

const PAGE = 30

/** Every notification, newest first, loaded a page at a time (the bell only shows the latest few). */
export function Notifications() {
  usePageTitle('Notifications')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const now = useNow()

  const feed = useInfiniteQuery({
    queryKey: ['notifications-all'],
    queryFn: ({ pageParam }) => api(`/notifications?limit=${PAGE}${pageParam ? `&before_id=${pageParam}` : ''}`),
    initialPageParam: null,
    getNextPageParam: (last) => (last.items.length === PAGE ? last.oldest_id : undefined),
  })
  const items = feed.data?.pages.flatMap((p) => p.items) ?? []
  const unread = feed.data?.pages[0]?.unread_count ?? 0

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['notifications'] })
    queryClient.invalidateQueries({ queryKey: ['notifications-all'] })
  }
  const markRead = useMutation({ mutationFn: (id) => api(`/notifications/${id}/read`, { method: 'POST' }), onSuccess: refresh })
  const markAll = useMutation({ mutationFn: () => api('/notifications/read-all', { method: 'POST' }), onSuccess: refresh })

  function open(n) {
    if (!n.read_at) markRead.mutate(n.id)
    if (n.listing_id) navigate(`/listings/${n.listing_id}`)
  }

  return (
    <section>
      <div className="notif-page-head">
        <h1>Notifications</h1>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => markAll.mutate()} disabled={unread === 0 || markAll.isPending}>
          Mark all as read
        </button>
      </div>

      {feed.isPending && <p className="muted center">Loading your notifications…</p>}
      {feed.isError && (
        <p className="error" role="alert">
          {errorMessage(feed.error)}{' '}
          <button type="button" className="link-button" onClick={() => feed.refetch()}>
            Try again
          </button>
        </p>
      )}
      {feed.isSuccess && items.length === 0 && (
        <div className="empty card">
          <p>Nothing yet. You'll be told when you're outbid, when an auction you follow is closing, and how it ended.</p>
          <Link to="/" className="btn btn-primary">
            Browse auctions
          </Link>
        </div>
      )}
      {items.length > 0 && (
        <ul className="notif-page-list">
          {items.map((n) => (
            <li key={n.id}>
              <button type="button" className={`bell-item ${n.read_at ? '' : 'bell-unread'}`} onClick={() => open(n)}>
                <span className="bell-title">{n.title}</span>
                {n.body && <span className="bell-body">{n.body}</span>}
                <span className="muted small">{timeAgo(n.created_at, now)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {feed.hasNextPage && (
        <div className="center">
          <button type="button" className="btn btn-ghost" onClick={() => feed.fetchNextPage()} disabled={feed.isFetchingNextPage}>
            {feed.isFetchingNextPage ? 'Loading…' : 'Load older notifications'}
          </button>
        </div>
      )}
    </section>
  )
}
