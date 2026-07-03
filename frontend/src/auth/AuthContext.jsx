import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import * as authApi from '../api/auth.js'
import * as parentsApi from '../api/parents.js'
import { clearToken, getToken, setToken } from '../api/client.js'
import { homePathForRole } from '../utils/roles.js'

const AuthContext = createContext(null)

// Roles allowed to sign in to this app. Any other role is rejected.
const ALLOWED_ROLES = ['parent', 'admin', 'teacher']

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null) // { id, name, email, role, must_change_password }
  const [parent, setParent] = useState(null) // Parent row; parents only
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  // While true, we don't yet know if the stored token is valid.
  const [bootstrapping, setBootstrapping] = useState(true)

  const logout = useCallback(() => {
    clearToken()
    setUser(null)
    setParent(null)
    setIsAuthenticated(false)
  }, [])

  // Loads the signed-in account: verifies role via /auth/me, and for parents
  // also loads the Parent row (needed for parent_id). Returns { me, parentProfile }.
  // Throws on any problem; callers decide messaging.
  const loadSession = useCallback(async () => {
    const me = await authApi.getMe()
    if (!ALLOWED_ROLES.includes(me.role)) {
      const err = new Error('Your account does not have access to this portal.')
      err.code = 'role_not_allowed'
      throw err
    }
    let parentProfile = null
    if (me.role === 'parent') {
      parentProfile = await parentsApi.getCurrentParent()
    }
    return { me, parentProfile }
  }, [])

  // On first load, if a token exists, validate it.
  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      if (!getToken()) {
        setBootstrapping(false)
        return
      }
      try {
        const { me, parentProfile } = await loadSession()
        if (!cancelled) {
          setUser(me)
          setParent(parentProfile)
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
  }, [loadSession, logout])

  // Any authenticated request that 401s broadcasts this event -> log out.
  useEffect(() => {
    window.addEventListener('auth:unauthorized', logout)
    return () => window.removeEventListener('auth:unauthorized', logout)
  }, [logout])

  const login = useCallback(
    async (email, password) => {
      const result = await authApi.login(email, password)

      // Store the token so the authenticated /auth/me check can use it.
      setToken(result.access_token)

      try {
        const { me, parentProfile } = await loadSession()
        setUser(me)
        setParent(parentProfile)
        setIsAuthenticated(true)
        return me
      } catch (err) {
        clearToken()
        setIsAuthenticated(false)
        if (err?.code === 'role_not_allowed') {
          throw new Error('Your account does not have access to this portal.')
        }
        if (err?.status === 404) {
          throw new Error('No parent profile is linked to this account. Please contact the school.')
        }
        if (err?.status === 0 || err?.status === 504) {
          throw err
        }
        throw new Error('Could not sign you in. Please try again.')
      }
    },
    [loadSession],
  )

  const refreshUser = useCallback(async () => {
    const me = await authApi.getMe()
    setUser(me)
    return me
  }, [])

  const role = user?.role ?? null
  const value = {
    user,
    parent,
    role,
    parentId: parent?.id ?? null,
    homePath: homePathForRole(role),
    isAuthenticated,
    bootstrapping,
    login,
    logout,
    refreshUser,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
