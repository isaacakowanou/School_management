import { apiDelete, apiGet, apiPost, apiPut } from './client.js'

// GET /api/v1/parents/me -> { id, user_id, name, email, phone }
export function getCurrentParent() {
  return apiGet('/parents/me')
}

// GET /api/v1/parents/{parent_id}/students -> [{ id, first_name, last_name, grade_level, student_number }]
export function getParentStudents(parentId) {
  return apiGet(`/parents/${parentId}/students`)
}

// GET /api/v1/parents (admin) -> [{ id, user_id, name, email, phone }]
export function listParents() {
  return apiGet('/parents')
}

// POST /api/v1/parents (admin)
export function createParent({ name, email, password, phone }) {
  const trimmedPhone = (phone || '').trim()
  return apiPost('/parents', {
    name: name.trim(),
    email: email.trim(),
    password: password.trim(),
    phone: trimmedPhone || null,
  })
}

// GET /api/v1/parents/{parent_id} (admin, or the parent themselves)
export function getParent(parentId) {
  return apiGet(`/parents/${parentId}`)
}

// PUT /api/v1/parents/{parent_id} (admin)
export function updateParent(parentId, { name, email, phone }) {
  const trimmedPhone = (phone || '').trim()
  return apiPut(`/parents/${parentId}`, {
    name: name.trim(),
    email: email.trim(),
    phone: trimmedPhone || null,
  })
}

// DELETE /api/v1/parents/{parent_id} (admin). Blocks when linked to active students.
export function deleteParent(parentId) {
  return apiDelete(`/parents/${parentId}`)
}
