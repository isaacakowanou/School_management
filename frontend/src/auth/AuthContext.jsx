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
      const err = new Error('role_not_allowed')
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

  useEffect(() => {
    const requirePasswordChange = () => {
      setUser((current) => (current ? { ...current, must_change_password: true } : current))
    }
    window.addEventListener('auth:password-change-required', requirePasswordChange)
    return () => window.removeEventListener('auth:password-change-required', requirePasswordChange)
  }, [])

  const login = useCallback(
    async (identifier, password) => {
      const result = await authApi.login(identifier, password)

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
          const accessError = new Error('role_not_allowed')
          accessError.code = 'role_not_allowed'
          throw accessError
        }
        if (err?.status === 404) {
          const profileError = new Error('parent_profile_missing')
          profileError.code = 'parent_profile_missing'
          throw profileError
        }
        if (err?.status === 0 || err?.status === 504) {
          throw err
        }
        const signInError = new Error('sign_in_failed')
        signInError.code = 'sign_in_failed'
        throw signInError
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
