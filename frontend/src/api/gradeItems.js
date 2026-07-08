import { apiDelete, apiGet, apiPost, apiPut } from './client.js'
import { isCanonicalTerm } from '../constants/terms.js'

// GET /api/v1/courses/{course_id}/grade-items
export function listGradeItems(courseId) {
  return apiGet(`/courses/${courseId}/grade-items`)
}

// POST /api/v1/grade-items (admin or assigned teacher).
// Weighted items: pass category, weight. Beninese items: pass itemType, omit category/weight.
export function createGradeItem(courseId, { title, category, maxScore, weight, term, dueDate, itemType }) {
  return apiPost('/grade-items', {
    course_id: courseId,
    title: title.trim(),
    category: category ? category.trim() : null,
    max_score: Number(maxScore),
    weight: weight !== '' && weight != null ? Number(weight) : null,
    term: term.trim(),
    due_date: dueDate ? dueDate : null,
    item_type: itemType || null,
  })
}

// PUT /api/v1/grade-items/{grade_item_id} (admin or assigned teacher).
// A non-canonical (legacy) term is omitted rather than sent: the backend only
// accepts the three trimesters, and omitting leaves the stored value unchanged.
// category/weight are nullable for Beninese items (backend ignores them in that mode).
export function updateGradeItem(gradeItemId, { title, category, maxScore, weight, term, dueDate }) {
  const body = {
    title: title.trim(),
    category: category ? category.trim() : null,
    max_score: Number(maxScore),
    weight: weight !== '' && weight != null ? Number(weight) : null,
    due_date: dueDate ? dueDate : null,
  }
  if (isCanonicalTerm(term.trim())) body.term = term.trim()
  return apiPut(`/grade-items/${gradeItemId}`, body)
}

// DELETE /api/v1/grade-items/{grade_item_id} (admin). Blocks when grades exist.
export function deleteGradeItem(gradeItemId) {
  return apiDelete(`/grade-items/${gradeItemId}`)
}
