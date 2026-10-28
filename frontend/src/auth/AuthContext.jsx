import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, getToken, onUnauthorized, setToken } from '../api/client'
import { AuthContext } from './context'

export function AuthProvider({ children }) {
  const queryClient = useQueryClient()
  const [token, setTokenState] = useState(getToken)

  const applyToken = useCallback(
    (next) => {
      setToken(next)
      setTokenState(next)
      // Cached data belongs to whoever was signed in before.
      queryClient.clear()
    },
    [queryClient],
  )

  const logout = useCallback(() => applyToken(null), [applyToken])

  // If the server ever rejects our token (expired, user deleted), sign out everywhere.
  useEffect(() => {
    onUnauthorized(logout)
    return () => onUnauthorized(null)
  }, [logout])

  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: () => api('/me'),
    enabled: token !== null,
    retry: false,
    staleTime: 60_000,
  })

  const login = useCallback(
    async (email, password) => {
      const result = await api('/auth/login', { method: 'POST', body: { email, password } })
      applyToken(result.access_token)
      return result
    },
    [applyToken],
  )

  const register = useCallback(
    async (email, displayName, password) => {
      const result = await api('/auth/register', {
        method: 'POST',
        body: { email, display_name: displayName, password },
      })
      applyToken(result.access_token)
      return result
    },
    [applyToken],
  )

  const refreshUser = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['me'] })
  }, [queryClient])

  const value = useMemo(
    () => ({
      user: token ? (meQuery.data ?? null) : null,
      loading: token !== null && meQuery.isPending,
      isSignedIn: token !== null,
      login,
      register,
      logout,
      refreshUser,
    }),
    [token, meQuery.data, meQuery.isPending, login, register, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
