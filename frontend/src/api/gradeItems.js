import { apiGet, apiPost, apiPut } from './client.js'

// GET /api/v1/courses/{course_id}/grade-items
// Read-only for the teacher portal in this pass.
export function listGradeItems(courseId) {
  return apiGet(`/courses/${courseId}/grade-items`)
}

// POST /api/v1/grade-items (admin or assigned teacher)
export function createGradeItem(courseId, { title, category, maxScore, weight, term }) {
  return apiPost('/grade-items', {
    course_id: courseId,
    title: title.trim(),
    category: category.trim(),
    max_score: Number(maxScore),
    weight: Number(weight),
    term: term.trim(),
  })
}

// PUT /api/v1/grade-items/{grade_item_id} (admin or assigned teacher)
export function updateGradeItem(gradeItemId, { title, category, maxScore, weight, term, dueDate }) {
  return apiPut(`/grade-items/${gradeItemId}`, {
    title: title.trim(),
    category: category.trim(),
    max_score: Number(maxScore),
    weight: Number(weight),
    term: term.trim(),
    due_date: dueDate ? dueDate : null,
  })
}
