import { apiDelete, apiGet, apiPost, apiPut } from './client.js'

// GET /api/v1/students (admin) -> [{ id, first_name, last_name, grade_level, student_number }]
export function listStudents({ academicStatus, schoolYear, classId } = {}) {
  const params = new URLSearchParams()
  if (academicStatus) params.set('academic_status', academicStatus)
  if (schoolYear) params.set('school_year', schoolYear)
  if (classId) params.set('class_id', classId)
  const qs = params.toString()
  return apiGet(`/students${qs ? `?${qs}` : ''}`)
}

// GET /api/v1/students/trash (admin) -> soft-deleted students
export function listDeletedStudents() {
  return apiGet('/students/trash')
}

// POST /api/v1/students (admin)
export function createStudent({ firstName, lastName, studentNumber, schoolLevel, classId, educmasterNumber }) {
  return apiPost('/students', {
    first_name: firstName.trim(),
    last_name: lastName.trim(),
    student_number: studentNumber.trim() || null,
    school_level: schoolLevel || null,
    class_id: classId || null,
    educmaster_number: (educmasterNumber || '').trim() || null,
  })
}

// GET /api/v1/students/{student_id}
export function getStudent(studentId) {
  return apiGet(`/students/${studentId}`)
}

// GET /api/v1/students/{student_id}/grades?term=... (admin only)
export function getStudentGrades(studentId, { schoolYear, term } = {}) {
  const params = new URLSearchParams()
  if (schoolYear) params.set('school_year', schoolYear)
  if (term) params.set('term', term)
  const qs = params.toString()
  return apiGet(`/students/${studentId}/grades${qs ? `?${qs}` : ''}`)
}

// DELETE /api/v1/students/{student_id} (admin) -> moves student to Trash
export function deleteStudent(studentId) {
  return apiDelete(`/students/${studentId}`)
}

// POST /api/v1/students/{student_id}/restore (admin)
export function restoreStudent(studentId) {
  return apiPost(`/students/${studentId}/restore`)
}

// PUT /api/v1/students/{student_id} (admin)
export function updateStudent(studentId, { firstName, lastName, studentNumber, schoolLevel, classId, educmasterNumber }) {
  return apiPut(`/students/${studentId}`, {
    first_name: firstName.trim(),
    last_name: lastName.trim(),
    student_number: studentNumber.trim(),
    school_level: schoolLevel || null,
    class_id: classId || null,
    educmaster_number: (educmasterNumber || '').trim() || null,
  })
}

// GET /api/v1/students/{student_id}/parents -> linked parents (LinkedParentResponse[])
export function getStudentParents(studentId) {
  return apiGet(`/students/${studentId}/parents`)
}

// POST /api/v1/students/{student_id}/parents (admin)
export function linkStudentParent(studentId, { parentId, relationship }) {
  const trimmedRelationship = (relationship || '').trim()
  return apiPost(`/students/${studentId}/parents`, {
    parent_id: parentId,
    relationship: trimmedRelationship || null,
  })
}

// DELETE /api/v1/students/{student_id}/parents/{parent_id} (admin)
export function unlinkStudentParent(studentId, parentId) {
  return apiDelete(`/students/${studentId}/parents/${parentId}`)
}
