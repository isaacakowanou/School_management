import { apiGet } from './client.js'

// GET /api/v1/teachers (admin) -> [{ id, user_id, name, email, employee_number }]
export function listTeachers() {
  return apiGet('/teachers')
}

// GET /api/v1/teachers/{teacher_id}
export function getTeacher(teacherId) {
  return apiGet(`/teachers/${teacherId}`)
}

// GET /api/v1/teachers/{teacher_id}/courses -> CourseResponse[]
export function getTeacherCourses(teacherId) {
  return apiGet(`/teachers/${teacherId}/courses`)
}
