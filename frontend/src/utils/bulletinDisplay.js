export function annualAverageLabel(annual, t) {
  if (annual?.is_partial) {
    return t('reports.annualAveragePartial', {
      complete: annual.complete_term_count,
      total: annual.total_term_count,
    })
  }
  return t('reports.annualAverage')
}
