import { apiGet, apiPost, apiPostPublic, apiPut, setToken } from './client.js'

// POST /api/v1/auth/login -> { access_token, token_type, role, user_id, must_change_password }
// identifier: email, employee number (teachers), or phone (parents)
export function login(identifier, password) {
  return apiPostPublic('/auth/login', { identifier, password })
}

// GET /api/v1/auth/me -> { id, name, email, role, must_change_password }
export function getMe() {
  return apiGet('/auth/me')
}

export function getProfile() {
  return apiGet('/auth/profile')
}

export function updateProfile({ name, phone }) {
  return apiPut('/auth/profile', { name: name.trim(), phone: (phone || '').trim() || null })
}

// POST /api/v1/auth/change-password
export async function changePassword(newPassword, currentPassword = null) {
  const result = await apiPost('/auth/change-password', {
    new_password: newPassword,
    current_password: currentPassword,
  })
  setToken(result.access_token)
  return result
}

// POST /api/v1/auth/forgot-password
// identifier: phone (parents) or employee number (teachers)
export function forgotPassword(identifier) {
  return apiPostPublic('/auth/forgot-password', { identifier })
}

// POST /api/v1/auth/reset-password
export function resetPassword(identifier, otp, newPassword) {
  return apiPostPublic('/auth/reset-password', { identifier, otp, new_password: newPassword })
}

export function resetPasswordByEmail(token, newPassword) {
  return apiPostPublic('/auth/reset-password/email', { token, new_password: newPassword })
}
