import { apiGet, apiPut } from './client.js'

export function listTrimesterLocks(schoolYear) {
  const params = new URLSearchParams({ school_year: schoolYear })
  return apiGet(`/trimester-locks?${params}`)
}

export function setTrimesterLock({ schoolYear, term, isLocked }) {
  return apiPut('/trimester-locks', {
    school_year: schoolYear,
    term,
    is_locked: isLocked,
  })
}
