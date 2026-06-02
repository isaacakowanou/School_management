import { apiGet, apiPost } from './client.js'

// GET /api/v1/course-results/{course_id} -> existing results for the course
export function listCourseResults(courseId) {
  return apiGet(`/course-results/${courseId}`)
}

// POST /api/v1/course-results/calculate/{course_id}
// Recalculates results; response includes calculated_count, results, and
// skipped_students (students missing one or more grades).
export function calculateCourseResults(courseId) {
  return apiPost(`/course-results/calculate/${courseId}`)
}
