import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useAuth } from '../auth/useAuth'

/** My saved alerts, plus add and remove. */
export function useWants() {
  const { isSignedIn } = useAuth()
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['wants'], queryFn: () => api('/me/wants'), enabled: isSignedIn, staleTime: 30_000 })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['wants'] })
  const add = useMutation({ mutationFn: (body) => api('/me/wants', { method: 'POST', body }), onSuccess: refresh })
  const remove = useMutation({ mutationFn: (id) => api(`/me/wants/${id}`, { method: 'DELETE' }), onSuccess: refresh })
  return { query, wants: query.data ?? [], add, remove }
}
