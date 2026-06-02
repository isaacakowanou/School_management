import { apiGet } from './client.js'

// GET /api/v1/students (admin) -> [{ id, first_name, last_name, grade_level, student_number }]
export function listStudents() {
  return apiGet('/students')
}

// GET /api/v1/students/{student_id}
export function getStudent(studentId) {
  return apiGet(`/students/${studentId}`)
}

// GET /api/v1/students/{student_id}/parents -> linked parents (LinkedParentResponse[])
export function getStudentParents(studentId) {
  return apiGet(`/students/${studentId}/parents`)
}
