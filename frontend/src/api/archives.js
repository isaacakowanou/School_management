import { apiGet } from './client.js'

export function listArchivedReports() {
  return apiGet('/archives/reports')
}

export function listArchivedCourses() {
  return apiGet('/archives/courses')
}

export function listArchivedStudents() {
  return apiGet('/archives/students')
}
