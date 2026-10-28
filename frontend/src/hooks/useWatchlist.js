import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/useAuth'

/** My saved auctions. Cards use `isWatching(id)`; the Watchlist page uses `items`. Signed-out visitors get an empty list. */
export function useWatchlist({ poll = false } = {}) {
  const { isSignedIn } = useAuth()
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => api('/me/watchlist'),
    enabled: isSignedIn,
    staleTime: 30_000,
    refetchInterval: poll ? 10_000 : false,
  })
  const items = query.data
  const ids = useMemo(() => new Set((items ?? []).map((c) => c.id)), [items])
  return { query, items: items ?? [], isWatching: (id) => ids.has(id), refresh: () => queryClient.invalidateQueries({ queryKey: ['watchlist'] }) }
}

/** Save or unsave one auction. While the request is in flight the button already shows the new state. */
export function useToggleWatch(listingId) {
  const { isWatching, refresh } = useWatchlist()
  const mutation = useMutation({
    mutationFn: (currentlyWatching) => api(`/listings/${listingId}/watch`, { method: currentlyWatching ? 'DELETE' : 'PUT' }),
    onSettled: refresh,
  })
  const saved = mutation.isPending ? !mutation.variables : isWatching(listingId)
  return { saved, toggle: () => mutation.mutate(isWatching(listingId)), pending: mutation.isPending, error: mutation.error }
}
