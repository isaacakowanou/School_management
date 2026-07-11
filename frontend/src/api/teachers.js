import { apiDelete, apiGet, apiPost, apiPut } from './client.js'

// GET /api/v1/teachers (admin) -> [{ id, user_id, name, email, employee_number }]
export function listTeachers() {
  return apiGet('/teachers')
}

// POST /api/v1/teachers (admin) -> { id, user_id, name, email, phone, employee_number, temp_password }
export function createTeacher({ name, email, phone, employeeNumber }) {
  return apiPost('/teachers', {
    name: name.trim(),
    email: email.trim() || null,
    phone: phone.trim() || null,
    employee_number: employeeNumber.trim() || null,
  })
}

// GET /api/v1/teachers/{teacher_id}
export function getTeacher(teacherId) {
  return apiGet(`/teachers/${teacherId}`)
}

// PUT /api/v1/teachers/{teacher_id} (admin)
export function updateTeacher(teacherId, { name, email, phone, employeeNumber }) {
  return apiPut(`/teachers/${teacherId}`, {
    name: name.trim(),
    email: email.trim() || null,
    phone: phone.trim() || null,
    employee_number: employeeNumber.trim(),
  })
}

// GET /api/v1/teachers/{teacher_id}/courses -> CourseResponse[]
export function getTeacherCourses(teacherId) {
  return apiGet(`/teachers/${teacherId}/courses`)
}

// DELETE /api/v1/teachers/{teacher_id} (admin). Blocks when courses or submitted grades exist.
export function deleteTeacher(teacherId) {
  return apiDelete(`/teachers/${teacherId}`)
}

export function resetTeacherPassword(teacherId) {
  return apiPost(`/teachers/${teacherId}/reset-password`)
}
