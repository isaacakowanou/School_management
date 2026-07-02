import { apiDelete, apiGet, apiPatch, apiPost } from './client.js'

// GET /api/v1/subjects (admin). Optional section / level_group / class_id
// filters; class_id narrows to the subjects applicable to that class.
export function listSubjects({ section, levelGroup, classId } = {}) {
  const params = new URLSearchParams()
  if (section) params.set('section', section)
  if (levelGroup) params.set('level_group', levelGroup)
  if (classId) params.set('class_id', classId)
  const qs = params.toString()
  return apiGet(`/subjects${qs ? `?${qs}` : ''}`)
}

// GET /api/v1/subjects/{subject_id}
export function getSubject(subjectId) {
  return apiGet(`/subjects/${subjectId}`)
}

// POST /api/v1/subjects (admin)
export function createSubject({ nameFr, nameEn, section, levelGroup, sortOrder, applicableClasses }) {
  return apiPost('/subjects', {
    name_fr: nameFr.trim(),
    name_en: nameEn.trim(),
    section,
    level_group: levelGroup,
    sort_order: sortOrder,
    applicable_classes: applicableClasses?.length ? applicableClasses : null,
  })
}

// PATCH /api/v1/subjects/{subject_id} (admin). Sends the full editable set;
// null applicable_classes widens the subject to its whole level group.
export function updateSubject(subjectId, { nameFr, nameEn, section, levelGroup, sortOrder, applicableClasses }) {
  return apiPatch(`/subjects/${subjectId}`, {
    name_fr: nameFr.trim(),
    name_en: nameEn.trim(),
    section,
    level_group: levelGroup,
    sort_order: sortOrder,
    applicable_classes: applicableClasses?.length ? applicableClasses : null,
  })
}

// DELETE /api/v1/subjects/{subject_id} (admin). 409 if courses reference it.
export function deleteSubject(subjectId) {
  return apiDelete(`/subjects/${subjectId}`)
}
