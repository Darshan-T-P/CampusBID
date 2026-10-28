import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { describeSuggestion } from '../lib/pricing'
import { formatRupees } from '../lib/format'
import { Icon } from './Icon'

/** On the Sell page: what similar items really sold for here, and a one-click starting price. */
export function PriceSuggestion({ category, condition, title, onUse }) {
  const words = useDebouncedValue(title.trim(), 600)
  const query = useQuery({
    queryKey: ['price-suggestion', category, condition, words],
    queryFn: () => {
      const params = new URLSearchParams({ category })
      if (condition) params.set('condition', condition)
      if (words) params.set('title', words)
      return api(`/pricing/suggestion?${params}`)
    },
    enabled: Boolean(category),
    staleTime: 60_000,
    retry: false,
  })
  if (!category || !query.data) return null

  const text = describeSuggestion(query.data, condition)
  if (!text) {
    return <p className="muted small price-hint">No similar sales on campus yet, so there is no price guide for this one.</p>
  }
  return (
    <div className="price-hint price-hint-found" role="status">
      <Icon name="trend" size={16} />
      <div>
        <strong>{text.sold}</strong>
        <span>{text.start}</span>
      </div>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => onUse(query.data.suggested_start)}>
        Use {formatRupees(query.data.suggested_start)}
      </button>
    </div>
  )
}
