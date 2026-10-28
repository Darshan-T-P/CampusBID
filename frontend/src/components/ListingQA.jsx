import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { errorMessage } from '../api/errors'
import { useAuth } from '../auth/useAuth'
import { Icon } from './Icon'
import { yearLabel } from '../lib/format'
import { findSimilarQuestion } from '../lib/questionSimilarity'

export function ListingQA({ listing }) {
  const { user, isSignedIn } = useAuth()
  const queryClient = useQueryClient()
  const listingId = String(listing.id)
  const isSeller = user != null && user.id === listing.seller.id

  const [questionText, setQuestionText] = useState('')
  const [askError, setAskError] = useState(null)
  const [askNotice, setAskNotice] = useState(null)

  // Reply state: map of questionId -> replyText
  const [replyDrafts, setReplyDrafts] = useState({})
  const [replyErrors, setReplyErrors] = useState({})

  const { data: questions = [], isPending } = useQuery({
    queryKey: ['questions', listingId],
    queryFn: () => api(`/listings/${listingId}/questions`),
  })

  const askMutation = useMutation({
    mutationFn: (text) => api(`/listings/${listingId}/questions`, { method: 'POST', body: { question_text: text } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['questions', listingId] })
      setQuestionText('')
      setAskError(null)
      setAskNotice('Your question has been posted! The seller will be notified.')
    },
    onError: (err) => {
      setAskNotice(null)
      setAskError(errorMessage(err))
    },
  })

  const answerMutation = useMutation({
    mutationFn: ({ questionId, text }) =>
      api(`/listings/${listingId}/questions/${questionId}/answer`, { method: 'POST', body: { answer_text: text } }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['questions', listingId] })
      setReplyDrafts((prev) => ({ ...prev, [variables.questionId]: '' }))
      setReplyErrors((prev) => ({ ...prev, [variables.questionId]: null }))
    },
    onError: (err, variables) => {
      setReplyErrors((prev) => ({ ...prev, [variables.questionId]: errorMessage(err) }))
    },
  })

  // Seller tools: hide spam from everyone else, pin a helpful answer to the top.
  const moderate = useMutation({
    mutationFn: ({ questionId, action, value }) =>
      api(`/listings/${listingId}/questions/${questionId}/${action}`, { method: 'POST', body: action === 'hide' ? { hidden: value } : { pinned: value } }),
    onSuccess: () => {
      setModerationError(null)
      queryClient.invalidateQueries({ queryKey: ['questions', listingId] })
    },
    onError: (err) => setModerationError(errorMessage(err)),
  })
  const [moderationError, setModerationError] = useState(null)

  // "Someone already asked something like this", shown while typing (never blocks asking).
  const similar = questionText.trim().length >= 12 ? findSimilarQuestion(questionText, questions) : null

  function handleAsk(e) {
    e.preventDefault()
    setAskNotice(null)
    if (!questionText.trim()) return
    askMutation.mutate(questionText)
  }

  function handleReply(e, questionId) {
    e.preventDefault()
    const text = replyDrafts[questionId]?.trim()
    if (!text) return
    answerMutation.mutate({ questionId, text })
  }

  return (
    <div className="listing-qa-section">
      <div className="qa-header">
        <h3 className="section-subtitle">
          Questions & Answers {questions.length > 0 && <span className="muted">({questions.length})</span>}
        </h3>
        <p className="qa-subtitle-hint">
          Ask condition details or specifications before placing a bid. Public answers help everyone bidding.
        </p>
      </div>

      {/* Seller guidance alert */}
      {isSeller && (
        <div className="qa-seller-tip-box">
          <Icon name="shield" size={16} />
          <div>
            <strong>Seller Dashboard: Questions</strong>
            <p>
              {questions.filter((q) => !q.answer_text).length > 0
                ? `${questions.filter((q) => !q.answer_text).length} unanswered question waiting for your reply below. Answers are visible to all students.`
                : 'No pending questions. Prospective buyers will ask questions here, and you will receive a notification to reply.'}
            </p>
          </div>
        </div>
      )}

      {/* Ask Question Box (for prospective buyers) */}
      {!isSeller && (
        <div className="ask-box card">
          {isSignedIn ? (
            user?.is_verified ? (
              <form onSubmit={handleAsk} className="ask-form">
                <label htmlFor="qa-input" className="ask-label">
                  <span>Ask the seller a question</span>
                  <span className="muted small">Visible to all students</span>
                </label>
                <div className="ask-input-row">
                  <input
                    id="qa-input"
                    type="text"
                    className="ask-input"
                    placeholder="e.g. Do the gears shift smoothly? Any scratches on screen?"
                    value={questionText}
                    onChange={(e) => {
                      setQuestionText(e.target.value)
                      setAskError(null)
                    }}
                    maxLength={500}
                    disabled={askMutation.isPending}
                  />
                  <button type="submit" className="btn btn-primary" disabled={askMutation.isPending || !questionText.trim()}>
                    {askMutation.isPending ? 'Posting…' : 'Ask Question'}
                  </button>
                </div>
                {similar && (
                  <div className="similar-hint" role="status">
                    <strong>Someone already asked something like this:</strong>
                    <span>“{similar.question_text}”</span>
                    <span className="muted small">{similar.answer_text ? `Seller's answer: ${similar.answer_text}` : 'Waiting for the seller to reply, so no need to ask again.'}</span>
                  </div>
                )}
                {askError && (
                  <div className="error-box" role="alert">
                    <Icon name="x" size={14} /> {askError}
                  </div>
                )}
                {askNotice && (
                  <div className="success-banner" role="status">
                    <Icon name="check" size={14} /> {askNotice}
                  </div>
                )}
              </form>
            ) : (
              <div className="warn-box">
                Verify your campus email to ask questions. <Link to="/verify">Verify email</Link>
              </div>
            )
          ) : (
            <div className="qa-login-cta">
              <p className="muted small">Have a question about this item before bidding?</p>
              <Link to="/login" className="btn btn-primary btn-sm">Sign in to ask</Link>
            </div>
          )}
        </div>
      )}

      {moderationError && (
        <p className="error small" role="alert">
          {moderationError}
        </p>
      )}

      {/* Questions Thread */}
      {isPending ? (
        <p className="muted">Loading questions…</p>
      ) : questions.length === 0 ? (
        <div className="qa-empty-state">
          <div className="qa-empty-icon"><Icon name="package" size={24} /></div>
          <h4>No questions asked yet</h4>
          <p className="muted small">
            Be the first to ask about item condition, usage history, or specs before bidding.
          </p>
        </div>
      ) : (
        <div className="qa-list">
          {questions.map((q) => {
            const askerInitials = q.asker_name
              ? q.asker_name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()
              : 'S'
            const draft = replyDrafts[q.id] || ''
            const err = replyErrors[q.id]

            return (
              <div key={q.id} className={`qa-card ${q.hidden ? 'qa-card-hidden' : ''} ${q.pinned ? 'qa-card-pinned' : ''}`}>
                {(q.pinned || q.hidden) && (
                  <div className="qa-flags">
                    {q.pinned && <span className="qa-flag qa-flag-pinned"><Icon name="bookmark" size={12} filled /> Pinned by the seller</span>}
                    {q.hidden && <span className="qa-flag qa-flag-hidden"><Icon name="eyeOff" size={12} /> Hidden from other students</span>}
                  </div>
                )}
                {/* Asker & Question */}
                <div className="qa-question-block">
                  <div className="qa-user-row">
                    <div className="qa-avatar">{askerInitials}</div>
                    <div className="qa-user-info">
                      <strong className="qa-user-name">{q.asker_name}</strong>
                      {(q.asker_year || q.asker_department) && (
                        <span className="qa-user-meta">
                          {[yearLabel(q.asker_year), q.asker_department].filter(Boolean).join(' · ')}
                        </span>
                      )}
                    </div>
                    <time className="qa-time muted small" dateTime={q.created_at}>
                      {new Date(q.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                    </time>
                  </div>
                  <p className="qa-question-text">{q.question_text}</p>
                </div>

                {isSeller && (
                  <div className="qa-moderation">
                    {q.answer_text && !q.hidden && (
                      <button type="button" className="btn btn-ghost btn-sm" disabled={moderate.isPending} onClick={() => moderate.mutate({ questionId: q.id, action: 'pin', value: !q.pinned })}>
                        {q.pinned ? 'Unpin' : 'Pin to top'}
                      </button>
                    )}
                    <button type="button" className="btn btn-ghost btn-sm" disabled={moderate.isPending} onClick={() => moderate.mutate({ questionId: q.id, action: 'hide', value: !q.hidden })}>
                      {q.hidden ? 'Show again' : 'Hide as spam'}
                    </button>
                  </div>
                )}

                {/* Seller Answer */}
                {q.answer_text ? (
                  <div className="qa-answer-block">
                    <div className="qa-answer-header">
                      <span className="qa-seller-badge">
                        <Icon name="shield" size={12} /> Seller Reply
                      </span>
                      <strong className="qa-seller-name">{listing.seller.display_name}</strong>
                      {q.answered_at && (
                        <time className="qa-time muted small" dateTime={q.answered_at}>
                          {new Date(q.answered_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                        </time>
                      )}
                    </div>
                    <p className="qa-answer-text">{q.answer_text}</p>
                  </div>
                ) : isSeller ? (
                  <form onSubmit={(e) => handleReply(e, q.id)} className="qa-reply-form">
                    <div className="qa-reply-input-row">
                      <input
                        type="text"
                        className="qa-reply-input"
                        placeholder="Reply publicly to this question…"
                        value={draft}
                        onChange={(e) =>
                          setReplyDrafts((prev) => ({ ...prev, [q.id]: e.target.value }))
                        }
                        disabled={answerMutation.isPending}
                      />
                      <button type="submit" className="btn btn-primary btn-sm" disabled={answerMutation.isPending || !draft.trim()}>
                        {answerMutation.isPending ? 'Replying…' : 'Reply'}
                      </button>
                    </div>
                    {err && (
                      <p className="error small" role="alert">
                        {err}
                      </p>
                    )}
                  </form>
                ) : (
                  <div className="qa-pending-chip">
                    <Icon name="clock" size={13} /> Waiting for seller reply
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
