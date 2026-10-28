import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { SALE_ACTIONS, actionsFor } from '../lib/sale'

/**
 * The seller's buttons for one listing. Anything irreversible asks "are you sure?" first.
 * `notice` ({ kind: 'ok' | 'error', text }) and `onNotice` live in the PAGE, not here: after an action
 * the listing jumps to another section, which recreates this component and would erase a local message.
 */
export function SellerActions({ listing, notice, onNotice }) {
  const queryClient = useQueryClient()
  const [asking, setAsking] = useState(null) // the action waiting for confirmation
  const [reason, setReason] = useState('')

  const run = useMutation({
    mutationFn: ({ action, body }) => api(`/listings/${listing.id}/${action}`, { method: 'POST', body }),
    onSuccess: (_, { action }) => {
      setAsking(null)
      setReason('')
      onNotice({ kind: 'ok', text: SALE_ACTIONS[action].success })
      for (const key of [['my-listings'], ['listing', String(listing.id)], ['listings'], ['my-bids']])
        queryClient.invalidateQueries({ queryKey: key })
    },
    onError: (e) => {
      setAsking(null)
      onNotice({ kind: 'error', text: errorMessage(e) }) // e.g. "This listing is already approved" when another tab got there first
      queryClient.invalidateQueries({ queryKey: ['my-listings'] })
    },
  })

  const actions = actionsFor(listing.status)
  if (actions.length === 0 && !notice) return null

  const go = (action) => run.mutate({ action, body: action === 'reject' ? { reason: reason.trim() || null } : undefined })
  const spec = asking ? SALE_ACTIONS[asking] : null

  return (
    <div className="actions">
      {!asking && (
        <div className="actions-row">
          {actions.map((action) => {
            const a = SALE_ACTIONS[action]
            return (
              <button
                key={action}
                type="button"
                className={`btn btn-sm ${a.style === 'primary' ? 'btn-primary' : 'btn-ghost btn-danger-text'}`}
                disabled={run.isPending}
                onClick={() => (a.confirm ? (onNotice(null), setAsking(action)) : go(action))}
              >
                {a.label}
              </button>
            )
          })}
        </div>
      )}

      {asking && (
        <div className="confirm-box" role="alertdialog" aria-label="Confirm">
          <p>{spec.confirm}</p>
          {spec.askReason && (
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
              placeholder="Reason (optional, shown publicly)"
              aria-label="Reason"
            />
          )}
          <div className="actions-row">
            <button type="button" className="btn btn-sm btn-danger" disabled={run.isPending} onClick={() => go(asking)}>
              {run.isPending ? 'Working…' : `Yes, ${spec.label.toLowerCase()}`}
            </button>
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setAsking(null)}>
              Keep it
            </button>
          </div>
        </div>
      )}

      {notice?.kind === 'ok' && <p className="success-box small" role="status">{notice.text}</p>}
      {notice?.kind === 'error' && <p className="error small" role="alert">{notice.text}</p>}
    </div>
  )
}
