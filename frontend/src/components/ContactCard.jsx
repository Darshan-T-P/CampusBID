import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { formatPhone, whatsappLink } from '../lib/phone'
import { Icon } from './Icon'

/**
 * The other side's contact number for an approved sale. Only the seller and the winner are ever sent it, so for
 * anyone else (the server answers 403) this simply renders nothing. `compact` is the one-line version for lists.
 */
export function ContactCard({ listingId, compact = false }) {
  const [copied, setCopied] = useState(false)
  const query = useQuery({
    queryKey: ['contact', listingId],
    queryFn: () => api(`/listings/${listingId}/contact`),
    retry: false,
    staleTime: 60_000,
  })
  const c = query.data
  if (!c) return null

  const label = c.role === 'seller' ? 'Seller' : 'Buyer'
  async function copy() {
    try {
      await navigator.clipboard.writeText(c.phone)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard blocked: the number is on screen anyway */
    }
  }

  return (
    <div className={`contact-card ${compact ? 'contact-compact' : ''}`}>
      <div className="contact-head">
        <Icon name="user" size={15} />
        <strong>{label}: {c.name}</strong>
      </div>
      {c.phone ? (
        <>
          <p className="contact-phone">{formatPhone(c.phone)}</p>
          <div className="contact-actions">
            <a className="btn btn-primary btn-sm" href={`tel:${c.phone}`}>Call</a>
            <a className="btn btn-ghost btn-sm" href={whatsappLink(c.phone)} target="_blank" rel="noreferrer">WhatsApp</a>
            <button type="button" className="btn btn-ghost btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
          </div>
        </>
      ) : (
        <p className="muted small">{c.name} hasn't added a mobile number. Agree the handover in person at the meet-up spot.</p>
      )}
      {!compact && <small className="muted">Shared only because this sale was approved. Use it to arrange the handover.</small>}
    </div>
  )
}

/** A nudge for people without a number, so the other side of a sale can reach them. */
export function AddPhoneHint({ user }) {
  if (!user || user.phone) return null
  return (
    <p className="muted small">
      You haven't added a mobile number. <Link to="/profile">Add one</Link> so the other person in a sale can reach you.
    </p>
  )
}
