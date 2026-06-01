import { apiGet, apiGetBlob } from './client.js'

// GET /api/v1/reports/student/{student_id}
// For parents the backend returns ONLY approved/sent reports.
export function getStudentReports(studentId) {
  return apiGet(`/reports/student/${studentId}`)
}

// GET /api/v1/reports/{report_id}
export function getReport(reportId) {
  return apiGet(`/reports/${reportId}`)
}

// GET /api/v1/reports/{report_id}/pdf -> Blob (requires Bearer auth)
export function downloadReportPdf(reportId) {
  return apiGetBlob(`/reports/${reportId}/pdf`)
}
