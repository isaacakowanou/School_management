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
