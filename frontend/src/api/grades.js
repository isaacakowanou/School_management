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

// POST /api/v1/courses/{courseId}/notify-grades -> fire grade notifications for changed students
export async function notifyGradesChanged(courseId, studentIds) {
  try {
    await apiPost(`/courses/${courseId}/notify-grades`, { student_ids: studentIds })
  } catch {
    // silent-fail: notification is best-effort, grades already saved
  }
}
