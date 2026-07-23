import { apiGet, apiPost } from './client.js'

// GET /api/v1/course-results/{course_id} -> existing results for the course
export function listCourseResults(courseId) {
  return apiGet(`/course-results/${courseId}`)
}

// GET /api/v1/course-results/student/{student_id} -> course results for a student
export function listStudentCourseResults(studentId) {
  return apiGet(`/course-results/student/${studentId}`)
}

// POST /api/v1/course-results/calculate/{course_id}
// Recalculates results; response includes calculated_count, results, and
// skipped_students (students missing one or more grades).
export function calculateCourseResults(courseId, { term } = {}) {
  const params = new URLSearchParams()
  if (term) params.set('term', term)
  const qs = params.toString()
  return apiPost(`/course-results/calculate/${courseId}${qs ? `?${qs}` : ''}`)
}

// POST /api/v1/course-results/calculate/{course_id}/students
// Recalculates results only for selected students.
export function calculateSelectedCourseResults(courseId, studentIds, { term } = {}) {
  const params = new URLSearchParams()
  if (term) params.set('term', term)
  const qs = params.toString()
  return apiPost(`/course-results/calculate/${courseId}/students${qs ? `?${qs}` : ''}`, {
    student_ids: studentIds,
  })
}
