import { apiGet, apiPost } from './client.js'

export function previewClassPassage(classId, { targetSchoolYear }) {
  const params = new URLSearchParams({ target_school_year: targetSchoolYear.trim() })
  return apiGet(`/passages/classes/${classId}?${params.toString()}`)
}

export function confirmPassage({ schoolYear, targetSchoolYear, classId, decisions }) {
  return apiPost('/passages/confirm', {
    school_year: schoolYear.trim(),
    target_school_year: targetSchoolYear.trim(),
    class_id: classId || null,
    decisions: decisions.map((decision) => ({
      student_id: decision.studentId,
      final_decision: decision.finalDecision,
      target_class_name: decision.targetClassName || null,
      note: decision.note?.trim() || null,
    })),
  })
}

export function getStudentPassageHistory(studentId) {
  return apiGet(`/passages/students/${studentId}/history`)
}
