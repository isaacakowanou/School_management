import { apiGet, apiPost } from './client.js'

// GET /api/v1/teachers (admin) -> [{ id, user_id, name, email, employee_number }]
export function listTeachers() {
  return apiGet('/teachers')
}

// POST /api/v1/teachers (admin)
export function createTeacher({ name, email, password, employeeNumber }) {
  return apiPost('/teachers', {
    name: name.trim(),
    email: email.trim(),
    password: password.trim(),
    employee_number: employeeNumber.trim(),
  })
}

// GET /api/v1/teachers/{teacher_id}
export function getTeacher(teacherId) {
  return apiGet(`/teachers/${teacherId}`)
}

// GET /api/v1/teachers/{teacher_id}/courses -> CourseResponse[]
export function getTeacherCourses(teacherId) {
  return apiGet(`/teachers/${teacherId}/courses`)
}
