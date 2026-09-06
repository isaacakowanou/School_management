import { apiDelete, apiGet, apiPost, apiPostForm, apiPut } from './client.js'

// GET /api/v1/parents/me -> { id, user_id, name, email, phone }
export function getCurrentParent() {
  return apiGet('/parents/me')
}

// PUT /api/v1/parents/me -> { id, user_id, name, email, phone }
export function updateCurrentParent({ name, phone }) {
  const body = {}
  if (name !== undefined) body.name = name.trim()
  if (phone !== undefined) body.phone = (phone || '').trim() || null
  return apiPut('/parents/me', body)
}

// GET /api/v1/parents/{parent_id}/students -> [{ id, first_name, last_name, grade_level, student_number }]
export function getParentStudents(parentId) {
  return apiGet(`/parents/${parentId}/students`)
}

// GET /api/v1/parents/me/students/{student_id}/grades?term=...
export function getParentStudentGrades(studentId, { schoolYear, term } = {}) {
  const params = new URLSearchParams()
  if (schoolYear) params.set('school_year', schoolYear)
  if (term) params.set('term', term)
  const qs = params.toString()
  return apiGet(`/parents/me/students/${studentId}/grades${qs ? `?${qs}` : ''}`)
}

// GET /api/v1/parents (admin) -> [{ id, user_id, name, email, phone }]
export function listParents() {
  return apiGet('/parents')
}

// POST /api/v1/parents (admin) -> { id, user_id, name, email, phone, temp_password }
export function createParent({ name, email, phone }) {
  const trimmedPhone = (phone || '').trim()
  return apiPost('/parents', {
    name: name.trim(),
    email: email.trim() || null,
    phone: trimmedPhone || null,
  })
}

// GET /api/v1/parents/{parent_id} (admin, or the parent themselves)
export function getParent(parentId) {
  return apiGet(`/parents/${parentId}`)
}

// PUT /api/v1/parents/{parent_id} (admin)
export function updateParent(parentId, { name, email, phone }) {
  const trimmedPhone = (phone || '').trim()
  return apiPut(`/parents/${parentId}`, {
    name: name.trim(),
    email: email.trim() || null,
    phone: trimmedPhone || null,
  })
}

// DELETE /api/v1/parents/{parent_id} (admin). Blocks when linked to active students.
export function deleteParent(parentId) {
  return apiDelete(`/parents/${parentId}`)
}

export function resetParentPassword(parentId) {
  return apiPost(`/parents/${parentId}/reset-password`)
}

export function previewParentLinkImport(file) {
  const formData = new FormData()
  formData.append('file', file)
  return apiPostForm('/parents/link-import/preview', formData)
}

export function commitParentLinkImport({ file, selectedRows }) {
  const formData = new FormData()
  formData.append('selected_rows', JSON.stringify(selectedRows))
  formData.append('file', file)
  return apiPostForm('/parents/link-import/commit', formData)
}
