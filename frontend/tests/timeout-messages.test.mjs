import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  REQUEST_FINISHED_EVENT,
  SLOW_REQUEST_EVENT,
  SLOW_REQUEST_THRESHOLD_MS,
  startSlowRequestTracking,
  updateSlowRequestIds,
} from '../src/api/requestActivity.js'

const readSource = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

function trackerHarness() {
  const events = []
  let timerCallback = null
  let scheduledDelay = null
  let cancelled = false
  const tracker = startSlowRequestTracking({
    eventTarget: { dispatchEvent: (event) => events.push(event) },
    schedule: (callback, delay) => {
      timerCallback = callback
      scheduledDelay = delay
      return 1
    },
    cancel: () => {
      cancelled = true
    },
    eventFactory: (type, requestId) => ({ type, detail: { requestId } }),
  })
  return {
    events,
    tracker,
    runTimer: () => timerCallback(),
    scheduledDelay: () => scheduledDelay,
    wasCancelled: () => cancelled,
  }
}

test('1-3: authenticated methods expire sessions while public auth POSTs stay public', () => {
  const client = readSource('src/api/client.js')
  const auth = readSource('src/api/auth.js')

  assert.match(client, /export async function apiPost[\s\S]*?response\.status === 401[\s\S]*?handleUnauthorized/)
  for (const helper of ['apiGet', 'apiPostForm', 'apiPut', 'apiPatch', 'apiDelete', 'apiGetBlob']) {
    const start = client.indexOf(`function ${helper}`)
    assert.notEqual(start, -1)
    assert.match(client.slice(start, start + 700), /response\.status === 401[\s\S]*?handleUnauthorized/)
  }
  assert.match(auth, /apiPostPublic\('\/auth\/login'/)
  assert.match(auth, /apiPostPublic\('\/auth\/forgot-password'/)
  assert.match(auth, /apiPostPublic\('\/auth\/reset-password'/)
  assert.match(auth, /apiPostPublic\('\/auth\/reset-password\/email'/)
  assert.match(auth, /apiPost\('\/auth\/change-password'/)
})

test('4-5: bootstrap and every protected role share the session-expiry notice', () => {
  const context = readSource('src/auth/AuthContext.jsx')
  const app = readSource('src/App.jsx')

  assert.match(context, /err\?\.status === 401\) expireSession\(\)/)
  assert.match(context, /addEventListener\('auth:unauthorized', expireSession\)/)
  assert.equal((app.match(/<RequireRole role="(?:admin|teacher|parent)">/g) || []).length, 3)
})

test('6-8: voluntary logout clears the notice, success clears it, and dismissal is exposed', () => {
  const context = readSource('src/auth/AuthContext.jsx')
  const login = readSource('src/pages/LoginPage.jsx')
  const logoutBlock = context.slice(context.indexOf('const logout'), context.indexOf('const expireSession'))

  assert.match(logoutBlock, /setSessionNotice\(null\)/)
  assert.doesNotMatch(logoutBlock, /session_expired/)
  assert.match(context, /setIsAuthenticated\(true\)[\s\S]*?setSessionNotice\(null\)[\s\S]*?return me/)
  assert.match(context, /dismissSessionNotice: \(\) => setSessionNotice\(null\)/)
  assert.match(login, /onClick=\{dismissSessionNotice\}/)
  assert.match(login, /err\.status === 401[\s\S]*?'login\.invalidCredentials'/)
})

test('9: slow tracking uses the approved ten-second threshold', () => {
  const harness = trackerHarness()
  assert.equal(SLOW_REQUEST_THRESHOLD_MS, 10_000)
  assert.equal(harness.scheduledDelay(), 10_000)
  assert.equal(harness.events.length, 0)
})

test('10: a request that finishes early never emits a slow event', () => {
  const harness = trackerHarness()
  harness.tracker.finish()
  harness.runTimer()

  assert.equal(harness.wasCancelled(), true)
  assert.deepEqual(harness.events.map((event) => event.type), [REQUEST_FINISHED_EVENT])
})

test('11: a slow request remains alive and clears its notice only when it finishes', () => {
  const harness = trackerHarness()
  harness.runTimer()
  assert.deepEqual(harness.events.map((event) => event.type), [SLOW_REQUEST_EVENT])

  harness.tracker.finish()
  assert.deepEqual(
    harness.events.map((event) => event.type),
    [SLOW_REQUEST_EVENT, REQUEST_FINISHED_EVENT],
  )
})

test('12: concurrent slow requests remain visible until every request finishes', () => {
  let ids = new Set()
  ids = updateSlowRequestIds(ids, SLOW_REQUEST_EVENT, 'a')
  ids = updateSlowRequestIds(ids, SLOW_REQUEST_EVENT, 'b')
  ids = updateSlowRequestIds(ids, REQUEST_FINISHED_EVENT, 'a')
  assert.deepEqual([...ids], ['b'])
  ids = updateSlowRequestIds(ids, REQUEST_FINISHED_EVENT, 'b')
  assert.equal(ids.size, 0)
})

test('13: the admin dashboard no longer treats a real 404 as server wake-up', () => {
  const dashboard = readSource('src/pages/AdminDashboardPage.jsx')
  assert.doesNotMatch(dashboard, /status === 404/)
  assert.match(dashboard, /setError\(err\.message\)/)
})

test('14: the global slow banner is mounted above routes with French and English copy', () => {
  const app = readSource('src/App.jsx')
  const banner = readSource('src/components/SlowServerBanner.jsx')
  const en = JSON.parse(readSource('src/locales/en.json'))
  const fr = JSON.parse(readSource('src/locales/fr.json'))

  assert.ok(app.indexOf('<SlowServerBanner />') < app.indexOf('<Routes>'))
  assert.match(banner, /role="status"/)
  assert.match(en.serverStatus.slow, /may be starting up/i)
  assert.match(en.serverStatus.slow, /up to a minute/i)
  assert.match(fr.serverStatus.slow, /peut être en cours de démarrage/i)
  assert.match(fr.serverStatus.slow, /jusqu’à une minute/i)
})
