import assert from 'node:assert/strict'
import test from 'node:test'


test('BUG A: four parent-link submissions execute one request', async () => {
  const { createSingleFlight } = await import('../src/utils/singleFlight.js')
  const runSingleFlight = createSingleFlight()
  let requests = 0

  const submit = () => runSingleFlight(async () => {
    requests += 1
    await new Promise((resolve) => setTimeout(resolve, 10))
    return 'linked'
  })

  const results = await Promise.all([submit(), submit(), submit(), submit()])

  assert.equal(requests, 1)
  assert.deepEqual(results, ['linked', 'linked', 'linked', 'linked'])
})


test('BUG C: empty classes still allow opening the enrollment preview', async () => {
  const { canOpenClassEnrollmentDialog } = await import('../src/utils/classEnrollment.js')

  assert.equal(
    canOpenClassEnrollmentDialog({ pending: false, studentCount: 0, courseCount: 0 }),
    true,
  )
  assert.equal(
    canOpenClassEnrollmentDialog({ pending: false, studentCount: 3, courseCount: 0 }),
    true,
  )
})


test('trimester view keeps historical items, scores, and results in their own section', async () => {
  const { assessmentDataForTerm } = await import('../src/utils/courseTrimester.js')
  const gradeItems = [
    { id: 'first-item', term: '1er Trimestre' },
    { id: 'third-item', term: '3ème Trimestre' },
  ]
  const grades = [
    { id: 'first-grade', grade_item_id: 'first-item' },
    { id: 'third-grade', grade_item_id: 'third-item' },
  ]
  const results = [
    { id: 'first-result', term: '1er Trimestre' },
    { id: 'third-result', term: '3ème Trimestre' },
  ]

  const historical = assessmentDataForTerm({
    term: '1er Trimestre',
    gradeItems,
    grades,
    results,
  })

  assert.deepEqual(historical.gradeItems.map((item) => item.id), ['first-item'])
  assert.deepEqual(historical.grades.map((grade) => grade.id), ['first-grade'])
  assert.deepEqual(historical.results.map((result) => result.id), ['first-result'])
})


test('grading-system change warns only when existing grade items could mismatch', async () => {
  const { gradingSystemChangeNeedsConfirmation } = await import('../src/utils/courseTrimester.js')

  assert.equal(gradingSystemChangeNeedsConfirmation({
    currentSystem: 'WEIGHTED', nextSystem: 'BENINESE', gradeItemCount: 3,
  }), true)
  assert.equal(gradingSystemChangeNeedsConfirmation({
    currentSystem: 'WEIGHTED', nextSystem: 'WEIGHTED', gradeItemCount: 3,
  }), false)
  assert.equal(gradingSystemChangeNeedsConfirmation({
    currentSystem: 'WEIGHTED', nextSystem: 'BENINESE', gradeItemCount: 0,
  }), false)
})


test('bulk generation summary includes every skipped-report count', async () => {
  const { bulkGenerationSummaryValues } = await import('../src/utils/reportGeneration.js')

  assert.deepEqual(
    bulkGenerationSummaryValues({
      totals: {
        generated_count: 7,
        skipped_existing_count: 40,
        skipped_no_results_count: 3,
        skipped_partial_count: 2,
        failed_count: 1,
      },
      unassigned_student_count: 4,
    }),
    {
      count: 7,
      existing: 40,
      noResults: 3,
      partial: 2,
      failed: 1,
      unassigned: 4,
    },
  )
})
