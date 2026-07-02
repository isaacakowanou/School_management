import { apiGet, apiPost, apiPut } from './client.js'
import { isCanonicalTerm } from '../constants/terms.js'

// GET /api/v1/courses/{course_id}/grade-items
export function listGradeItems(courseId) {
  return apiGet(`/courses/${courseId}/grade-items`)
}

// POST /api/v1/grade-items (admin or assigned teacher)
export function createGradeItem(courseId, { title, category, maxScore, weight, term, dueDate }) {
  return apiPost('/grade-items', {
    course_id: courseId,
    title: title.trim(),
    category: category.trim(),
    max_score: Number(maxScore),
    weight: Number(weight),
    term: term.trim(),
    due_date: dueDate ? dueDate : null,
  })
}

// PUT /api/v1/grade-items/{grade_item_id} (admin or assigned teacher).
// A non-canonical (legacy) term is omitted rather than sent: the backend only
// accepts the three trimesters, and omitting leaves the stored value unchanged.
export function updateGradeItem(gradeItemId, { title, category, maxScore, weight, term, dueDate }) {
  const body = {
    title: title.trim(),
    category: category.trim(),
    max_score: Number(maxScore),
    weight: Number(weight),
    due_date: dueDate ? dueDate : null,
  }
  if (isCanonicalTerm(term.trim())) body.term = term.trim()
  return apiPut(`/grade-items/${gradeItemId}`, body)
}
