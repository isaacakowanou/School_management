export const SLOW_REQUEST_THRESHOLD_MS = 10_000
export const SLOW_REQUEST_EVENT = 'api:request-slow'
export const REQUEST_FINISHED_EVENT = 'api:request-finished'

let nextRequestId = 0

function browserRequestEvent(type, requestId) {
  return new CustomEvent(type, { detail: { requestId } })
}

export function startSlowRequestTracking({
  eventTarget = window,
  schedule = window.setTimeout.bind(window),
  cancel = window.clearTimeout.bind(window),
  eventFactory = browserRequestEvent,
  threshold = SLOW_REQUEST_THRESHOLD_MS,
} = {}) {
  const requestId = `request-${nextRequestId += 1}`
  let finished = false
  const timerId = schedule(() => {
    if (!finished) eventTarget.dispatchEvent(eventFactory(SLOW_REQUEST_EVENT, requestId))
  }, threshold)

  return {
    requestId,
    finish() {
      if (finished) return
      finished = true
      cancel(timerId)
      eventTarget.dispatchEvent(eventFactory(REQUEST_FINISHED_EVENT, requestId))
    },
  }
}

export function updateSlowRequestIds(current, eventType, requestId) {
  const next = new Set(current)
  if (eventType === SLOW_REQUEST_EVENT) next.add(requestId)
  if (eventType === REQUEST_FINISHED_EVENT) next.delete(requestId)
  return next
}
