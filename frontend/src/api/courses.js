import { apiDelete, apiGet, apiPost, apiPut } from './client.js'
import { isCanonicalTerm } from '../constants/terms.js'

// GET /api/v1/courses
// For teachers the backend returns ONLY the courses assigned to them.
export function getMyCourses() {
  return apiGet('/courses')
}

// GET /api/v1/courses/{course_id}
export function getCourse(courseId) {
  return apiGet(`/courses/${courseId}`)
}

// GET /api/v1/courses/{course_id}/students -> students enrolled in the course
export function listCourseStudents(courseId) {
  return apiGet(`/courses/${courseId}/students`)
}

// GET /api/v1/courses (admin -> all courses). Same endpoint as getMyCourses,
// named for the admin context where every course is returned. Optional
// school_year filter.
export function listCourses({ schoolYear } = {}) {
  const params = new URLSearchParams()
  if (schoolYear) params.set('school_year', schoolYear)
  const qs = params.toString()
  return apiGet(`/courses${qs ? `?${qs}` : ''}`)
}

// POST /api/v1/courses (admin). With a subjectId the backend derives name and
// language_group from the subject, so neither is sent (a conflicting value
// would be rejected with a 422).
export function createCourse({ name, code, teacherId, gradeLevel, term, schoolYear, languageGroup, classId, subjectId }) {
  return apiPost('/courses', {
    name: subjectId ? null : name.trim(),
    code: code.trim(),
    teacher_id: teacherId,
    grade_level: gradeLevel.trim(),
    term: term.trim(),
    school_year: schoolYear.trim(),
    language_group: subjectId ? null : languageGroup || null,
    class_id: classId || null,
    subject_id: subjectId || null,
  })
}

// PUT /api/v1/courses/{course_id} (admin). Same subject rule as createCourse:
// with a subjectId, name / language_group are omitted so the backend derives
// them from the subject.
export function updateCourse(courseId, { name, code, teacherId, gradeLevel, term, schoolYear, languageGroup, classId, subjectId }) {
  const body = {
    code: code.trim(),
    teacher_id: teacherId,
    grade_level: gradeLevel.trim(),
    school_year: schoolYear.trim(),
    class_id: classId || null,
    subject_id: subjectId || null,
  }
  // A non-canonical (legacy) term is omitted rather than sent: the backend
  // only accepts the three trimesters, and omitting leaves it unchanged.
  if (isCanonicalTerm(term.trim())) body.term = term.trim()
  if (!subjectId) {
    body.name = name.trim()
    body.language_group = languageGroup || null
  }
  return apiPut(`/courses/${courseId}`, body)
}

// POST /api/v1/courses/clone-year (admin). Duplicates all courses from one
// school year into another (no grade items, no enrollments). 409 if the
// target year already has courses.
export function cloneYearCourses({ sourceYear, targetYear }) {
  return apiPost('/courses/clone-year', {
    source_year: sourceYear.trim(),
    target_year: targetYear.trim(),
  })
}

// POST /api/v1/enrollments (admin)
export function enrollStudentInCourse(courseId, studentId) {
  return apiPost('/enrollments', {
    course_id: courseId,
    student_id: studentId,
  })
}

// DELETE /api/v1/courses/{course_id}/students/{student_id} (admin)
export function unenrollStudentFromCourse(courseId, studentId) {
  return apiDelete(`/courses/${courseId}/students/${studentId}`)
}
