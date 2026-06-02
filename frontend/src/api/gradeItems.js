import { apiGet } from './client.js'

// GET /api/v1/courses/{course_id}/grade-items
// Read-only for the teacher portal in this pass.
export function listGradeItems(courseId) {
  return apiGet(`/courses/${courseId}/grade-items`)
}
