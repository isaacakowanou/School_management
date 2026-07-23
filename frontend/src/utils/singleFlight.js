export function createSingleFlight() {
  let inFlight = null

  return function runSingleFlight(operation) {
    if (inFlight) return inFlight
    inFlight = Promise.resolve()
      .then(operation)
      .finally(() => {
        inFlight = null
      })
    return inFlight
  }
}
