import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import * as authApi from '../api/auth.js'
import * as parentsApi from '../api/parents.js'
import { clearToken, getToken, setToken } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [parent, setParent] = useState(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  // While true, we don't yet know if the stored token is valid.
  const [bootstrapping, setBootstrapping] = useState(true)

  const logout = useCallback(() => {
    clearToken()
    setParent(null)
    setIsAuthenticated(false)
  }, [])

  // On first load, if a token exists, validate it: confirm the account is a
  // parent via /auth/me, then load the Parent profile.
  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      if (!getToken()) {
        setBootstrapping(false)
        return
      }
      try {
        const me = await authApi.getMe()
        if (me.role !== 'parent') {
          if (!cancelled) logout()
          return
        }
        const profile = await parentsApi.getCurrentParent()
        if (!cancelled) {
          setParent(profile)
          setIsAuthenticated(true)
        }
      } catch {
        if (!cancelled) logout()
      } finally {
        if (!cancelled) setBootstrapping(false)
      }
    }
    bootstrap()
    return () => {
      cancelled = true
    }
  }, [logout])

  // Any authenticated request that 401s broadcasts this event -> log out.
  useEffect(() => {
    window.addEventListener('auth:unauthorized', logout)
    return () => window.removeEventListener('auth:unauthorized', logout)
  }, [logout])

  const login = useCallback(async (email, password) => {
    const result = await authApi.login(email, password)

    // Store the token so the authenticated /auth/me check can use it.
    setToken(result.access_token)

    // Confirm the account role via the authoritative /auth/me endpoint.
    let me
    try {
      me = await authApi.getMe()
    } catch {
      clearToken()
      setIsAuthenticated(false)
      throw new Error('Could not verify your account. Please try again.')
    }

    // Reject non-parent accounts (keeps non-parents out of the portal).
    if (me.role !== 'parent') {
      clearToken()
      setIsAuthenticated(false)
      throw new Error('This portal is for parents only. Please use a parent account.')
    }

    // Load the Parent row (provides the parent_id used by later calls).
    try {
      const profile = await parentsApi.getCurrentParent()
      setParent(profile)
      setIsAuthenticated(true)
      return profile
    } catch (err) {
      clearToken()
      setIsAuthenticated(false)
      if (err?.status === 404) {
        throw new Error('No parent profile is linked to this account. Please contact the school.')
      }
      throw new Error('Could not load your parent profile. Please try again.')
    }
  }, [])

  const value = {
    parent,
    parentId: parent?.id ?? null,
    isAuthenticated,
    bootstrapping,
    login,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
