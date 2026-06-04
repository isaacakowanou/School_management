import { apiGet, apiPost } from './client.js'

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

// GET /api/v1/courses (admin -> all courses). Same endpoint as getMyCourses,
// named for the admin context where every course is returned.
export function listCourses() {
  return apiGet('/courses')
}

// POST /api/v1/courses (admin)
export function createCourse({ name, code, teacherId, gradeLevel, term, schoolYear }) {
  return apiPost('/courses', {
    name: name.trim(),
    code: code.trim(),
    teacher_id: teacherId,
    grade_level: gradeLevel.trim(),
    term: term.trim(),
    school_year: schoolYear.trim(),
  })
}
