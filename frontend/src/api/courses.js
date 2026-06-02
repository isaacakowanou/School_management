import { apiGet } from './client.js'

// GET /api/v1/courses
// For teachers the backend returns ONLY the courses assigned to them.
export function getMyCourses() {
  return apiGet('/courses')
}

// GET /api/v1/courses/{course_id}
export function getCourse(courseId) {
  return apiGet(`/courses/${courseId}`)
}

// GET /api/v1/courses/{course_id}/students -> students enrolled in the course
export function listCourseStudents(courseId) {
  return apiGet(`/courses/${courseId}/students`)
}
