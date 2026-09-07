// Authentication/error boundary for every frontend API call. Callers replace
// the stored JWT with fresh tokens returned after login/password changes.
// detail.code takes precedence over X-Error-Code, and both resolve through the
// active locale; raw backend English stays diagnostic-only and an unmapped or
// absent code becomes localized request_failed. Authenticated 401s clear the
// token globally, while login 401s remain ordinary invalid-credential errors.

import i18n from '../i18n.js'
import { startSlowRequestTracking } from './requestActivity.js'

const API_BASE = '/api/v1'
const TOKEN_KEY = 'parent_portal_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  // Replacement, rather than token accumulation, is required by the backend's
  // token_version session-kill contract after password changes.
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(status, message, detail = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function authHeaders(extra = {}) {
  const headers = { ...extra }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

// Resolve backend error codes through i18n. Raw server text remains available
// in `detail` for diagnostics but is never rendered as user-facing copy.
function errorMessage(detail, status, code) {
  if (code) return i18n.t(`apiErrors.${code}`, { defaultValue: i18n.t('apiErrors.request_failed') })
  if (typeof detail === 'string') return i18n.t('apiErrors.request_failed')
  if (Array.isArray(detail) && detail.length > 0) {
    return i18n.t('apiErrors.validation_error')
  }
  return i18n.t('apiErrors.request_failed', { status })
}

async function parseError(response) {
  let detail = null
  try {
    const data = await response.json()
    detail = data?.detail ?? null
  } catch {
    detail = null
  }
  const headerCode = response.headers.get('X-Error-Code')
  const detailCode = detail && !Array.isArray(detail) && typeof detail === 'object' ? detail.code : null
  const code = detailCode || headerCode || (Array.isArray(detail) ? 'validation_error' : 'request_failed')
  const normalizedDetail = detailCode || !headerCode ? detail : { code: headerCode, message: detail }
  const error = new ApiError(response.status, errorMessage(detail, response.status, code), normalizedDetail)
  error.code = code
  return error
}

async function parseAndHandleError(response) {
  const error = await parseError(response)
  if (response.status === 403 && error.detail?.code === 'password_change_required') {
    window.dispatchEvent(new CustomEvent('auth:password-change-required'))
  }
  return error
}

async function rawFetch(path, options) {
  const requestActivity = startSlowRequestTracking()
  try {
    return await fetch(`${API_BASE}${path}`, options)
  } catch {
    throw new ApiError(0, i18n.t('apiErrors.network_error'))
  } finally {
    requestActivity.finish()
  }
}

// Used by authenticated GETs. A 401 here means an expired/invalid session,
// so we clear the token and broadcast so AuthContext can redirect to login.
function handleUnauthorized() {
  clearToken()
  window.dispatchEvent(new CustomEvent('auth:unauthorized'))
  return new ApiError(401, i18n.t('apiErrors.session_expired'))
}

export async function apiGet(path) {
  const response = await rawFetch(path, {
    method: 'GET',
    headers: authHeaders({ Accept: 'application/json' }),
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseAndHandleError(response)
  return response.json()
}

export async function apiPost(path, body) {
  const response = await rawFetch(path, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json', Accept: 'application/json' }),
    body: body != null ? JSON.stringify(body) : undefined,
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseAndHandleError(response)
  return response.json()
}

// Public authentication calls must not turn a login/reset failure into an
// authenticated-session expiry or attach a stale bearer token.
export async function apiPostPublic(path, body) {
  const response = await rawFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body != null ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) throw await parseAndHandleError(response)
  return response.json()
}

// Authenticated multipart POST. The browser supplies the multipart boundary;
// setting Content-Type manually would produce an unreadable upload body.
export async function apiPostForm(path, formData) {
  const response = await rawFetch(path, {
    method: 'POST',
    headers: authHeaders({ Accept: 'application/json' }),
    body: formData,
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseAndHandleError(response)
  return response.json()
}

// Authenticated PUT follows the same global 401 boundary as other writes.
export async function apiPut(path, body) {
  const response = await rawFetch(path, {
    method: 'PUT',
    headers: authHeaders({ 'Content-Type': 'application/json', Accept: 'application/json' }),
    body: body != null ? JSON.stringify(body) : undefined,
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseAndHandleError(response)
  return response.json()
}

// Authenticated PATCH (partial update). Like apiPut, a 401 here means an
// expired session and triggers the global logout.
export async function apiPatch(path, body) {
  const response = await rawFetch(path, {
    method: 'PATCH',
    headers: authHeaders({ 'Content-Type': 'application/json', Accept: 'application/json' }),
    body: body != null ? JSON.stringify(body) : undefined,
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseAndHandleError(response)
  return response.json()
}

export async function apiDelete(path) {
  const response = await rawFetch(path, {
    method: 'DELETE',
    headers: authHeaders({ Accept: 'application/json' }),
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseAndHandleError(response)
  return response.json()
}

export async function apiGetBlob(path) {
  const response = await rawFetch(path, {
    method: 'GET',
    headers: authHeaders(),
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseAndHandleError(response)
  return response.blob()
}
