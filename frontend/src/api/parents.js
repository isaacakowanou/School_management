import { apiGet } from './client.js'

// GET /api/v1/parents/me -> { id, user_id, name, email, phone }
export function getCurrentParent() {
  return apiGet('/parents/me')
}

// GET /api/v1/parents/{parent_id}/students -> [{ id, first_name, last_name, grade_level, student_number }]
export function getParentStudents(parentId) {
  return apiGet(`/parents/${parentId}/students`)
}
