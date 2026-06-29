export function formatScore20(value) {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toFixed(2)} / 20`
}

// Formats a report average according to the report's grade scale.
// Historical reports ("100") render as a percentage; post-A1.2 reports ("20")
// render on the /20 scale.
export function formatReportAverage(value, scale) {
  if (value === null || value === undefined) return '—'
  if (scale === '100') return `${Number(value).toFixed(2)}%`
  return `${Number(value).toFixed(2)} / 20`
}

export function formatGpa(value) {
  if (value === null || value === undefined) return '—'
  return Number(value).toFixed(2)
}
