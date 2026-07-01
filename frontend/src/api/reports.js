import { apiGet, apiGetBlob, apiPatch, apiPost, apiPut } from './client.js'

// GET /api/v1/reports/student/{student_id}
// For parents the backend returns ONLY approved/sent reports.
export function getStudentReports(studentId) {
  return apiGet(`/reports/student/${studentId}`)
}

// GET /api/v1/reports/{report_id}
export function getReport(reportId) {
  return apiGet(`/reports/${reportId}`)
}

// GET /api/v1/reports/admin/{report_id} -> admin detail with student display fields
export function getAdminReport(reportId) {
  return apiGet(`/reports/admin/${reportId}`)
}

// GET /api/v1/reports/{report_id}/staleness (admin only)
export function getReportStaleness(reportId) {
  return apiGet(`/reports/${reportId}/staleness`)
}

// GET /api/v1/reports/{report_id}/pdf -> Blob (requires Bearer auth)
export function downloadReportPdf(reportId) {
  return apiGetBlob(`/reports/${reportId}/pdf`)
}

// --- Admin report management ---

// GET /api/v1/reports (admin only) -> all report cards
export function listReports() {
  return apiGet('/reports')
}

// POST /api/v1/reports/generate/{student_id} -> creates an admin draft report
export function generateReport(studentId, { term, schoolYear }) {
  return apiPost(`/reports/generate/${studentId}`, {
    term,
    school_year: schoolYear,
  })
}

// PUT /api/v1/reports/{report_id}/summary -> save an edited parent-facing summary
export function updateReportSummary(reportId, aiSummary) {
  return apiPut(`/reports/${reportId}/summary`, { ai_summary: aiSummary })
}

// POST /api/v1/reports/{report_id}/approve -> move draft to approved
export function approveReport(reportId) {
  return apiPost(`/reports/${reportId}/approve`)
}

// POST /api/v1/reports/{report_id}/send -> email approved report to parents
export function sendReport(reportId) {
  return apiPost(`/reports/${reportId}/send`)
}

// POST /api/v1/reports/{report_id}/regenerate -> rebuild snapshot as draft (admin only)
export function regenerateReport(reportId) {
  return apiPost(`/reports/${reportId}/regenerate`)
}

// PATCH /api/v1/reports/{report_id} -> update conduct/work-habit items + comments (admin only)
export function updateReportDetails(reportId, payload) {
  return apiPatch(`/reports/${reportId}`, payload)
}
