import { apiDelete, apiGet, apiPost } from './client.js'

export function listTrash({ entityType } = {}) {
  const params = new URLSearchParams()
  if (entityType) params.set('entity_type', entityType)
  const qs = params.toString()
  return apiGet(`/admin/trash${qs ? `?${qs}` : ''}`)
}

export function restoreTrashEntry(entryId) {
  return apiPost(`/admin/trash/${encodeURIComponent(entryId)}/restore`)
}

export function purgeTrashEntry(entryId) {
  return apiDelete(`/admin/trash/${encodeURIComponent(entryId)}`)
}

export function emptyTrash() {
  return apiDelete('/admin/trash')
}
