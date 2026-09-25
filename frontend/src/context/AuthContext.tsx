import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api, tokenStore } from '../lib/api'
import type { User } from '../types'

interface AuthContextValue {
  user: User | null
  /** True until the initial "am I still logged in?" check finishes. */
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // On first load, a token may already be in localStorage. Validate it against
  // /api/auth/me rather than trusting it: it might be expired or revoked.
  useEffect(() => {
    let cancelled = false

    const restore = async () => {
      if (!tokenStore.get()) {
        setLoading(false)
        return
      }
      try {
        const currentUser = await api.me()
        if (!cancelled) setUser(currentUser)
      } catch {
        tokenStore.clear()
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void restore()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.login(email, password)
    tokenStore.set(response.access_token)
    setUser(response.user)
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    const response = await api.register(email, password)
    tokenStore.set(response.access_token)
    setUser(response.user)
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside an AuthProvider')
  return context
}