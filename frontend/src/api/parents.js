import { apiGet } from './client.js'

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

// GET /api/v1/parents/{parent_id} (admin, or the parent themselves)
export function getParent(parentId) {
  return apiGet(`/parents/${parentId}`)
}
