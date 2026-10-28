import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { playBidChime, playLeaderChime } from '../lib/sound'

/**
 * Hook to subscribe to real-time Server-Sent Events (SSE) for an auction.
 * Replaces slow polling with immediate push notifications on new bids,
 * countdown extensions, or status updates, with audio feedback and price flash.
 */
export function useAuctionStream(listingId, currentUserId) {
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState(null)

  useEffect(() => {
    if (!listingId) return

    const streamUrl = `/api/listings/${listingId}/stream`
    let eventSource = null

    try {
      eventSource = new EventSource(streamUrl)

      eventSource.addEventListener('connect', () => {
        setIsConnected(true)
      })

      eventSource.addEventListener('bid', (e) => {
        try {
          const payload = JSON.parse(e.data)
          setIsConnected(true)
          setLastEvent({ type: 'bid', timestamp: Date.now(), data: payload })

          // Play audio feedback
          if (payload.listing && currentUserId && payload.listing.leading_bidder) {
            playLeaderChime()
          } else {
            playBidChime()
          }

          // Immediately update TanStack query cache with the new listing data
          if (payload.listing) {
            queryClient.setQueryData(['listing', String(listingId)], payload.listing)
          }

          // Invalidate related lists so bid tables refresh instantaneously
          queryClient.invalidateQueries({ queryKey: ['bids', String(listingId)] })
          queryClient.invalidateQueries({ queryKey: ['auto-bids', String(listingId)] })
          queryClient.invalidateQueries({ queryKey: ['my-bids'] })
          queryClient.invalidateQueries({ queryKey: ['listings'] })
        } catch {
          // Bad payload, ignore
        }
      })

      // The auction changed state (approved, handed over, cancelled): the event carries the fresh listing.
      eventSource.addEventListener('status', (e) => {
        try {
          const payload = JSON.parse(e.data)
          if (payload.listing) queryClient.setQueryData(['listing', String(listingId)], payload.listing)
        } catch {
          /* a bad payload: the next poll corrects it */
        }
        queryClient.invalidateQueries({ queryKey: ['my-bids'] })
        queryClient.invalidateQueries({ queryKey: ['my-listings'] })
        queryClient.invalidateQueries({ queryKey: ['notifications'] })
      })

      // The timer ran out and the server closed the auction: refresh at once instead of at the next poll.
      eventSource.addEventListener('closed', () => {
        queryClient.invalidateQueries({ queryKey: ['listing', String(listingId)] })
        queryClient.invalidateQueries({ queryKey: ['bids', String(listingId)] })
        queryClient.invalidateQueries({ queryKey: ['my-bids'] })
        queryClient.invalidateQueries({ queryKey: ['my-listings'] })
        queryClient.invalidateQueries({ queryKey: ['listings'] })
        queryClient.invalidateQueries({ queryKey: ['notifications'] })
      })

      eventSource.addEventListener('question_asked', () => {
        queryClient.invalidateQueries({ queryKey: ['questions', String(listingId)] })
        queryClient.invalidateQueries({ queryKey: ['notifications'] })
      })

      eventSource.addEventListener('question_answered', () => {
        queryClient.invalidateQueries({ queryKey: ['questions', String(listingId)] })
        queryClient.invalidateQueries({ queryKey: ['notifications'] })
      })

      eventSource.onerror = () => {
        setIsConnected(false)
        // Browser EventSource automatically attempts reconnection
      }
    } catch {
      // EventSource failed
    }

    return () => {
      if (eventSource) {
        eventSource.close()
      }
    }
  }, [listingId, queryClient, currentUserId])

  return { isConnected, lastEvent }
}
