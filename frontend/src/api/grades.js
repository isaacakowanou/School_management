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

// POST /api/v1/courses/{courseId}/grades/batch -> create/update/delete grade cells.
// An entry with score: null clears the existing score.
export function saveCourseGradesBatch(courseId, entries) {
  return apiPost(`/courses/${courseId}/grades/batch`, { entries })
}

// POST /api/v1/courses/{courseId}/notify-grades -> fire grade notifications for changed students
export async function notifyGradesChanged(courseId, studentIds) {
  return apiPost(`/courses/${courseId}/notify-grades`, { student_ids: studentIds })
}
