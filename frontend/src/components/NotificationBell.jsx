import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useNow } from '../hooks/useNow'
import { timeAgo } from '../lib/format'

const POLL_MS = 5000
const MAX_POPUPS = 3 // a burst shows a few, not a wall of pop-ups

const canPopUp = () => typeof Notification !== 'undefined'

/** Bell in the top bar: unread badge, a dropdown of notifications, and opt-in desktop pop-ups. */
export function NotificationBell() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const now = useNow()
  const [open, setOpen] = useState(false)
  const [permission, setPermission] = useState(canPopUp() ? Notification.permission : 'denied')
  const wrap = useRef(null)
  const lastSeen = useRef(null) // highest notification id we have already looked at

  const feed = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api('/notifications?limit=20'),
    refetchInterval: POLL_MS,
    // Pop-ups are for a tab nobody is looking at, so polling must carry on in the background. By default the
    // query library pauses interval polling while a tab is hidden, which would silence exactly those alerts.
    refetchIntervalInBackground: true,
  })
  const items = feed.data?.items ?? []
  const unread = feed.data?.unread_count ?? 0

  // Desktop pop-ups for notifications that arrived since the last check, only while the tab is in the
  // background (if you're looking at the page, the badge is enough). The first load just records where
  // we are, so old notifications are never replayed as pop-ups.
  useEffect(() => {
    if (!feed.data) return
    const maxId = feed.data.items.reduce((m, n) => Math.max(m, n.id), 0)
    if (lastSeen.current === null) {
      lastSeen.current = maxId
      return
    }
    const fresh = feed.data.items.filter((n) => n.id > lastSeen.current && !n.read_at).sort((a, b) => a.id - b.id)
    lastSeen.current = Math.max(lastSeen.current, maxId)
    if (fresh.length === 0 || !document.hidden || !canPopUp() || Notification.permission !== 'granted') return
    for (const n of fresh.slice(-MAX_POPUPS)) {
      const popup = new Notification(n.title, { body: n.body, tag: `relay-${n.id}` })
      popup.onclick = () => {
        window.focus()
        if (n.listing_id) navigate(`/listings/${n.listing_id}`)
        popup.close()
      }
    }
  }, [feed.data, navigate])

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => wrap.current && !wrap.current.contains(e.target) && setOpen(false)
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['notifications'] })
  const markRead = useMutation({ mutationFn: (id) => api(`/notifications/${id}/read`, { method: 'POST' }), onSuccess: refresh })
  const markAll = useMutation({ mutationFn: () => api('/notifications/read-all', { method: 'POST' }), onSuccess: refresh })

  function openItem(n) {
    if (!n.read_at) markRead.mutate(n.id)
    setOpen(false)
    if (n.listing_id) navigate(`/listings/${n.listing_id}`)
  }

  async function enableAlerts() {
    setPermission(await Notification.requestPermission())
  }

  return (
    <div className="bell-wrap" ref={wrap}>
      <button
        type="button"
        className="bell-btn"
        onClick={() => setOpen((o) => !o)}
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.7 21a2 2 0 0 1-3.4 0" />
        </svg>
        {unread > 0 && <span className="bell-badge">{unread > 9 ? '9+' : unread}</span>}
      </button>

      {open && (
        <div className="bell-panel" role="region" aria-label="Notifications">
          <div className="bell-head">
            <strong>Notifications</strong>
            <button type="button" className="link-button" onClick={() => markAll.mutate()} disabled={unread === 0}>
              Mark all as read
            </button>
          </div>

          {items.length === 0 ? (
            <p className="muted bell-empty">Nothing yet. You'll be told when you're outbid, when an auction you follow is about to close, and how it ended.</p>
          ) : (
            <ul className="bell-list">
              {items.map((n) => (
                <li key={n.id}>
                  <button type="button" className={`bell-item ${n.read_at ? '' : 'bell-unread'}`} onClick={() => openItem(n)}>
                    <span className="bell-title">{n.title}</span>
                    {n.body && <span className="bell-body">{n.body}</span>}
                    <span className="muted small">{timeAgo(n.created_at, now)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {canPopUp() && (
            <div className="bell-foot">
              {permission === 'granted' && <span className="muted small">Desktop alerts are on (shown when this tab is in the background).</span>}
              {permission === 'default' && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={enableAlerts}>
                  Enable desktop alerts
                </button>
              )}
              {permission === 'denied' && <span className="muted small">Desktop alerts are blocked in your browser settings.</span>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
