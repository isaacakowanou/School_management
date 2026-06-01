import { apiGet, apiPost } from './client.js'

// POST /api/v1/auth/login -> { access_token, token_type, role, user_id }
export function login(email, password) {
  return apiPost('/auth/login', { email, password })
}

// GET /api/v1/auth/me -> { id, name, email, role }
export function getMe() {
  return apiGet('/auth/me')
}
