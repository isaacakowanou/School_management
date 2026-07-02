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
