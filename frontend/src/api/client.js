// Tiny fetch wrapper: prefixes /api/v1, attaches the JWT, normalizes errors,
// and signals global 401s so the app can log out.

const API_BASE = '/api/v1'
const TOKEN_KEY = 'parent_portal_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
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

// FastAPI error details come in three shapes: a plain string (HTTPException),
// a list of {loc, msg, ...} objects (Pydantic validation), or an object with
// a message field (structured 409s). Surface a readable message for each so
// users never see a bare "Request failed (422)".
function errorMessage(detail, status) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const msg = detail[0]?.msg
    if (typeof msg === 'string') return msg.replace(/^Value error, /, '')
  }
  if (detail && typeof detail.message === 'string') return detail.message
  return `Request failed (${status})`
}

async function parseError(response) {
  let detail = null
  try {
    const data = await response.json()
    detail = data?.detail ?? null
  } catch {
    detail = null
  }
  return new ApiError(response.status, errorMessage(detail, response.status), detail)
}

async function rawFetch(path, options) {
  try {
    return await fetch(`${API_BASE}${path}`, options)
  } catch {
    throw new ApiError(0, 'Could not reach the server. Is the backend running?')
  }
}

// Used by authenticated GETs. A 401 here means an expired/invalid session,
// so we clear the token and broadcast so AuthContext can redirect to login.
function handleUnauthorized() {
  clearToken()
  window.dispatchEvent(new CustomEvent('auth:unauthorized'))
  return new ApiError(401, 'Your session has expired. Please sign in again.')
}

export async function apiGet(path) {
  const response = await rawFetch(path, {
    method: 'GET',
    headers: authHeaders({ Accept: 'application/json' }),
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseError(response)
  return response.json()
}

// Login uses this. A 401 here is "bad credentials", NOT session expiry,
// so it intentionally does not trigger the global logout.
export async function apiPost(path, body) {
  const response = await rawFetch(path, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json', Accept: 'application/json' }),
    body: body != null ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) throw await parseError(response)
  return response.json()
}

// Authenticated PUT. Unlike apiPost (used by login), a 401 here means an
// expired session, so it triggers the global logout like apiGet.
export async function apiPut(path, body) {
  const response = await rawFetch(path, {
    method: 'PUT',
    headers: authHeaders({ 'Content-Type': 'application/json', Accept: 'application/json' }),
    body: body != null ? JSON.stringify(body) : undefined,
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseError(response)
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
  if (!response.ok) throw await parseError(response)
  return response.json()
}

export async function apiDelete(path) {
  const response = await rawFetch(path, {
    method: 'DELETE',
    headers: authHeaders({ Accept: 'application/json' }),
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseError(response)
  return response.json()
}

export async function apiGetBlob(path) {
  const response = await rawFetch(path, {
    method: 'GET',
    headers: authHeaders(),
  })
  if (response.status === 401) throw handleUnauthorized()
  if (!response.ok) throw await parseError(response)
  return response.blob()
}
