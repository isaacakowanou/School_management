import { formatReportAverage } from '../utils/format.js'

// A1.6 three averages. Renders three cards (Moyenne française / anglaise /
// bilingue) when the report carries the new fields. Historical reports predate
// the feature (all three null) and fall back to the single legacy Overall
// average card so older /100 snapshots still render. Returns bare `.stat`
// cards; the caller supplies the wrapping `.summary-row`.
export default function ReportAverages({ report }) {
  const hasLanguageAverages =
    report.french_average != null ||
    report.english_average != null ||
    report.bilingual_average != null

  if (!hasLanguageAverages) {
    return (
      <div className="stat">
        <div className="stat-label">Overall average</div>
        <div className="stat-value">{formatReportAverage(report.overall_average, report.scale)}</div>
      </div>
    )
  }

  return (
    <>
      <div className="stat">
        <div className="stat-label">Moyenne française</div>
        <div className="stat-value">{formatReportAverage(report.french_average, report.scale)}</div>
      </div>
      <div className="stat">
        <div className="stat-label">Moyenne anglaise</div>
        <div className="stat-value">{formatReportAverage(report.english_average, report.scale)}</div>
      </div>
      <div className="stat">
        <div className="stat-label">Moyenne bilingue</div>
        <div className="stat-value">{formatReportAverage(report.bilingual_average, report.scale)}</div>
      </div>
    </>
  )
}
