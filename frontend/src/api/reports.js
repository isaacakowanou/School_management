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
export function generateReport(studentId, { term, schoolYear, generatePartial = false }) {
  return apiPost(`/reports/generate/${studentId}`, {
    term,
    school_year: schoolYear,
    generate_partial: generatePartial,
  })
}

// PUT /api/v1/reports/{report_id}/summary -> save an edited parent-facing summary
export function updateReportSummary(reportId, aiSummary) {
  return apiPut(`/reports/${reportId}/summary`, { ai_summary: aiSummary })
}

// POST /api/v1/reports/{report_id}/approve -> move draft to approved
export function approveReport(reportId, { approveStale = false } = {}) {
  return apiPost(`/reports/${reportId}/approve`, { approve_stale: approveStale })
}

// POST /api/v1/reports/{report_id}/send -> email approved report to parents
export function sendReport(reportId, { sendStale = false } = {}) {
  return apiPost(`/reports/${reportId}/send`, { send_stale: sendStale })
}

// POST /api/v1/reports/{report_id}/regenerate -> rebuild snapshot as draft (admin only)
export function regenerateReport(reportId) {
  return apiPost(`/reports/${reportId}/regenerate`)
}

// PATCH /api/v1/reports/{report_id} -> update conduct/work-habit items + comments (admin only)
export function updateReportDetails(reportId, payload) {
  return apiPatch(`/reports/${reportId}`, payload)
}

// --- Conseil de classe: class-scoped status + batch actions (admin only) ---

// GET /api/v1/reports/class-status -> one row per student of the class
export function getClassReportStatus({ classId, schoolYear, term }) {
  const params = new URLSearchParams({ class_id: classId, school_year: schoolYear, term })
  return apiGet(`/reports/class-status?${params}`)
}

function classBatchBody({
  classId,
  schoolYear,
  term,
  generatePartial = false,
  approveStale = false,
  sendStale = false,
}) {
  return {
    class_id: classId,
    school_year: schoolYear,
    term,
    generate_partial: generatePartial,
    approve_stale: approveStale,
    send_stale: sendStale,
  }
}

// POST /api/v1/reports/batch-generate -> drafts for every student with results and no report
export function batchGenerateReports(args) {
  return apiPost('/reports/batch-generate', classBatchBody(args))
}

// POST /api/v1/reports/batch-approve -> approves DRAFT reports only
export function batchApproveReports(args) {
  return apiPost('/reports/batch-approve', classBatchBody(args))
}

// POST /api/v1/reports/batch-send -> sends approved reports (marked sent only on notification success)
export function batchSendReports(args) {
  return apiPost('/reports/batch-send', classBatchBody(args))
}

// POST /api/v1/reports/class-pdf -> enqueue a merged class-PDF render job
export function createClassPdfJob(args) {
  return apiPost('/reports/class-pdf', classBatchBody(args))
}

// GET /api/v1/reports/class-pdf/{job_id} -> JSON status while pending/failed,
// the PDF blob once done. The caller polls until it gets a pdf.
export async function pollClassPdfJob(jobId) {
  const blob = await apiGetBlob(`/reports/class-pdf/${jobId}`)
  if (blob.type === 'application/pdf') {
    return { status: 'done', blob }
  }
  const body = JSON.parse(await blob.text())
  return { status: body.status, error: body.error || null }
}
