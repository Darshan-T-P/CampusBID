import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, mediaUrl } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { Countdown } from '../components/Countdown'
import { Icon } from '../components/Icon'
import { MAX_CHARS, SUGGESTIONS, canSend, plainText, toApiMessages, withProposalState } from '../lib/assistantChat'
import { formatRupees } from '../lib/format'
import { usePageTitle } from '../hooks/usePageTitle'

const STORE = 'relay.assistant'

function loadChat() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORE) ?? '[]')
    return Array.isArray(saved) ? saved : []
  } catch {
    return []
  }
}

function saveChat(messages) {
  try {
    sessionStorage.setItem(STORE, JSON.stringify(messages.slice(-30)))
  } catch {
    /* storage unavailable: the chat just won't survive leaving the page */
  }
}

/** A small result row: enough to judge an auction and open it. */
function ResultCard({ listing }) {
  const { user } = useAuth()
  return (
    <li>
      <Link to={`/listings/${listing.id}`} className="assist-result">
        <span className="assist-result-thumb">{listing.thumbnail ? <img src={mediaUrl(listing.thumbnail)} alt="" loading="lazy" /> : <Icon name="package" size={20} />}</span>
        <span className="assist-result-main">
          <strong>{listing.title}{user?.id === listing.seller_id && <span className="chip assist-own">Your listing</span>}</strong>
          <span className="muted small">
            {formatRupees(listing.price)} · {listing.bid_count} {listing.bid_count === 1 ? 'bid' : 'bids'} · <Countdown closesAt={listing.closes_at} />
          </span>
        </span>
      </Link>
    </li>
  )
}

/** The assistant has only PREPARED this. Nothing happens until the student presses Confirm. */
function ProposalCard({ proposal, state, onConfirm, onDismiss }) {
  const status = state?.status ?? 'pending'
  return (
    <div className={`assist-proposal assist-proposal-${status}`}>
      <div className="assist-proposal-head">
        <Icon name="gavel" size={16} />
        <strong>Automatic bid on {proposal.title}</strong>
      </div>
      {status === 'done' ? (
        <p className="success">
          Done. The app will now bid for you on <Link to={`/listings/${proposal.listing_id}`}>this auction</Link>, up to {formatRupees(proposal.max_amount)}.
        </p>
      ) : status === 'dismissed' ? (
        <p className="muted small">Dismissed. Nothing was set.</p>
      ) : (
        <>
          <p>
            Bid for me as little as needed, up to <strong>{formatRupees(proposal.max_amount)}</strong>. Next bid must be at least {formatRupees(proposal.min_next_bid)}
            {proposal.current_price != null ? `; it's at ${formatRupees(proposal.current_price)} now.` : '.'}
          </p>
          <small className="muted">Your maximum is public, and the app never goes above it. Nothing happens until you confirm.</small>
          {state?.error && <p className="error" role="alert">{state.error}</p>}
          <div className="form-actions">
            <button type="button" className="btn btn-primary btn-sm" onClick={onConfirm} disabled={status === 'confirming'}>
              {status === 'confirming' ? 'Setting…' : `Confirm up to ${formatRupees(proposal.max_amount)}`}
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onDismiss} disabled={status === 'confirming'}>
              Dismiss
            </button>
          </div>
        </>
      )}
    </div>
  )
}

export function Assistant() {
  usePageTitle('Assistant')
  const queryClient = useQueryClient()
  const [messages, setMessages] = useState(loadChat)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const end = useRef(null)
  const status = useQuery({ queryKey: ['assistant-status'], queryFn: () => api('/assistant/status'), staleTime: 60_000 })

  useEffect(() => {
    saveChat(messages)
  }, [messages])
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' }) // braces: an effect must return nothing but a cleanup function
  }, [messages, busy])

  async function send(text) {
    const content = text.trim()
    if (!canSend(content, busy)) return
    const next = [...messages, { role: 'user', content }]
    setMessages(next)
    setDraft('')
    setError(null)
    setBusy(true)
    try {
      const reply = await api('/assistant/chat', { method: 'POST', body: { messages: toApiMessages(next) } })
      setMessages([...next, { role: 'assistant', content: reply.reply, listings: reply.listings, proposals: reply.proposals }])
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function confirm(index, proposal) {
    setMessages((m) => withProposalState(m, index, proposal.listing_id, { status: 'confirming' }))
    try {
      // The same call the "Automatic bidding" box on the auction page makes, made by the student, so every normal rule applies.
      await api(`/listings/${proposal.listing_id}/auto-bid`, { method: 'PUT', body: { max_amount: proposal.max_amount } })
      setMessages((m) => withProposalState(m, index, proposal.listing_id, { status: 'done' }))
      queryClient.invalidateQueries({ queryKey: ['my-auto-bids'] })
      queryClient.invalidateQueries({ queryKey: ['my-bids'] })
      queryClient.invalidateQueries({ queryKey: ['listing', String(proposal.listing_id)] })
    } catch (e) {
      setMessages((m) => withProposalState(m, index, proposal.listing_id, { status: 'pending', error: errorMessage(e) }))
    }
  }

  const dismiss = (index, proposal) => setMessages((m) => withProposalState(m, index, proposal.listing_id, { status: 'dismissed' }))
  const clear = () => {
    setMessages([])
    setError(null)
  }

  if (status.data && !status.data.enabled) {
    return (
      <section>
        <h1>Assistant</h1>
        <div className="empty card">
          <p>The assistant isn't set up on this server yet. Add a GROQ_API_KEY to the backend settings to switch it on.</p>
        </div>
      </section>
    )
  }

  return (
    <section className="assist">
      <div className="assist-head">
        <div>
          <h1>Assistant</h1>
          <p className="muted">Tell it what you're after, like "a cycle under ₹2,000". It searches the open auctions for you, and can prepare an automatic bid for you to confirm.</p>
        </div>
        {messages.length > 0 && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={clear}>
            New chat
          </button>
        )}
      </div>

      <div className="card assist-chat">
        <div className="assist-log" aria-live="polite">
          {messages.length === 0 && (
            <div className="assist-empty">
              <p className="muted">Try one of these:</p>
              <div className="assist-chips">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="chip chip-button" onClick={() => send(s)} disabled={busy}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`assist-msg assist-${m.role}`}>
              <div className="assist-bubble">{m.role === 'assistant' ? plainText(m.content) : m.content}</div>
              {m.role === 'assistant' && m.listings?.length > 0 && (
                <ul className="assist-results">
                  {m.listings.map((l) => (
                    <ResultCard key={l.id} listing={l} />
                  ))}
                </ul>
              )}
              {m.role === 'assistant' &&
                m.proposals?.map((p) => (
                  <ProposalCard key={p.listing_id} proposal={p} state={m.proposalStates?.[p.listing_id]} onConfirm={() => confirm(i, p)} onDismiss={() => dismiss(i, p)} />
                ))}
            </div>
          ))}
          {busy && <div className="assist-msg assist-assistant"><div className="assist-bubble muted">Looking…</div></div>}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <div ref={end} />
        </div>

        <form
          className="assist-form"
          onSubmit={(e) => {
            e.preventDefault()
            send(draft)
          }}
        >
          <input
            aria-label="Message the assistant"
            placeholder="e.g. find me a cycle under ₹2,000"
            value={draft}
            maxLength={MAX_CHARS}
            onChange={(e) => setDraft(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />
          <button className="btn btn-primary" disabled={!canSend(draft, busy)}>
            Send
          </button>
        </form>
        <small className="muted">It can search and suggest. It never bids unless you press Confirm, never goes above the amount you give it, and can't see other students' details.</small>
      </div>
    </section>
  )
}
