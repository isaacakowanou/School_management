import { apiGet, apiPost, apiPut } from './client.js'

// GET /api/v1/courses/{course_id}/grades -> all grades for the course
export function listCourseGrades(courseId) {
  return apiGet(`/courses/${courseId}/grades`)
}

// POST /api/v1/grades -> create a grade for a (student, grade_item)
export function createGrade({ studentId, gradeItemId, score }) {
  return apiPost('/grades', {
    student_id: studentId,
    grade_item_id: gradeItemId,
    score,
  })
}

// PUT /api/v1/grades/{grade_id} -> update an existing grade's score
export function updateGrade(gradeId, score) {
  return apiPut(`/grades/${gradeId}`, { score })
}
