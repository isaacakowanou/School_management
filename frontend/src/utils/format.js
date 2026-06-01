export function formatPercent(value) {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toFixed(2)}%`
}

export function formatGpa(value) {
  if (value === null || value === undefined) return '—'
  return Number(value).toFixed(2)
}
