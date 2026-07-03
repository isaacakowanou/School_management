import { apiGet, apiPost } from './client.js'

// POST /api/v1/auth/login -> { access_token, token_type, role, user_id, must_change_password }
export function login(email, password) {
  return apiPost('/auth/login', { email, password })
}

// GET /api/v1/auth/me -> { id, name, email, role, must_change_password }
export function getMe() {
  return apiGet('/auth/me')
}

// POST /api/v1/auth/change-password
export function changePassword(newPassword) {
  return apiPost('/auth/change-password', { new_password: newPassword })
}
