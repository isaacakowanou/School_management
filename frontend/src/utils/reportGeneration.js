export function bulkGenerationSummaryValues(result) {
  const totals = result?.totals || {}

  return {
    count: totals.generated_count || 0,
    existing: totals.skipped_existing_count || 0,
    noResults: totals.skipped_no_results_count || 0,
    partial: totals.skipped_partial_count || 0,
    failed: totals.failed_count || 0,
    unassigned: result?.unassigned_student_count || 0,
  }
}
