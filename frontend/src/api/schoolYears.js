import { apiPost } from './client.js'

export function createSchoolYear({ schoolYear, cloneCourses = false, sourceSchoolYear = null }) {
  return apiPost('/school-years', {
    school_year: schoolYear.trim(),
    clone_courses: cloneCourses,
    source_school_year: sourceSchoolYear?.trim() || null,
  })
}
