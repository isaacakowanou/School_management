import { apiPost } from './client.js'

// POST /api/v1/ai/check-report/{report_card_id} (admin only)
// Runs the deterministic checker and returns a list of AI warnings.
export function checkReport(reportId) {
  return apiPost(`/ai/check-report/${reportId}`)
}

// POST /api/v1/ai/generate-summary/{report_card_id} (admin only)
// Generates a parent-friendly summary and stores it on the draft report.
export function generateReportSummary(reportId) {
  return apiPost(`/ai/generate-summary/${reportId}`)
}
