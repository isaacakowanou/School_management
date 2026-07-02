import { apiDelete, apiGet, apiPatch, apiPost } from './client.js'

// GET /api/v1/classes (admin). Optional school_year / school_level filters.
export function listClasses({ schoolYear, schoolLevel } = {}) {
  const params = new URLSearchParams()
  if (schoolYear) params.set('school_year', schoolYear)
  if (schoolLevel) params.set('school_level', schoolLevel)
  const qs = params.toString()
  return apiGet(`/classes${qs ? `?${qs}` : ''}`)
}

// GET /api/v1/classes/{class_id}
export function getClass(classId) {
  return apiGet(`/classes/${classId}`)
}

// POST /api/v1/classes (admin)
export function createClass({ nameFr, nameEn, schoolLevel, stream, sortOrder, schoolYear }) {
  return apiPost('/classes', {
    name_fr: nameFr.trim(),
    name_en: nameEn?.trim() || null,
    school_level: schoolLevel,
    stream: stream?.trim() || null,
    sort_order: sortOrder,
    school_year: schoolYear.trim(),
  })
}

// PATCH /api/v1/classes/{class_id} (admin). Sends the full editable set; empty
// name_en / stream clear via the backend's model_fields_set handling.
export function updateClass(classId, { nameFr, nameEn, schoolLevel, stream, sortOrder, schoolYear }) {
  return apiPatch(`/classes/${classId}`, {
    name_fr: nameFr.trim(),
    name_en: nameEn?.trim() || null,
    school_level: schoolLevel,
    stream: stream?.trim() || null,
    sort_order: sortOrder,
    school_year: schoolYear.trim(),
  })
}

// DELETE /api/v1/classes/{class_id} (admin). 409 if students/courses assigned.
export function deleteClass(classId) {
  return apiDelete(`/classes/${classId}`)
}

// POST /api/v1/classes/bulk-create (admin). Creates all 18 GGFK taxonomy
// classes for the year; already-existing ones (normalized-name match) are
// skipped. Returns { status, created: [...], skipped: [...] }.
export function bulkCreateClasses({ schoolYear }) {
  return apiPost('/classes/bulk-create', { school_year: schoolYear.trim() })
}

// GET /api/v1/classes/{class_id}/enrollment-preview (admin). Returns the
// counts the bulk-enroll action would produce (students × courses, split into
// to-create vs already-existing). status: "ok" when both sides have >=1 row,
// "empty" when either is 0.
export function previewClassEnrollments(classId) {
  return apiGet(`/classes/${classId}/enrollment-preview`)
}

// POST /api/v1/classes/{class_id}/bulk-enroll (admin). Enrolls every student
// in the class into every course tagged with the class AND the class's
// school_year. Idempotent — existing (student, course) pairs are skipped.
export function bulkEnrollClassStudents(classId) {
  return apiPost(`/classes/${classId}/bulk-enroll`, null)
}
